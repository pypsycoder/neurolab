"""Private control-plane dashboard; authentication is provided by Tailscale Serve."""
import json
import os
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import psycopg
import redis
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ["REDIS_URL"]
REFRESH_SECONDS = int(os.getenv("PANEL_REFRESH_SECONDS", "10"))
TASK_QUEUE = "neuro-lab:tasks"
MAX_QUEUE_DEPTH = max(1, int(os.getenv("DASHBOARD_MAX_QUEUE_DEPTH", "100")))
MAX_TASKS_PER_LANE_PER_DAY = max(
    1, int(os.getenv("DASHBOARD_MAX_TASKS_PER_LANE_PER_DAY", "50"))
)
CHAT_MODELS = (
    "GigaChat-2",
    "GigaChat-2-Max",
    "GigaChat-2-Pro",
    "GigaChat-3-Lightning",
    "GigaChat-3-Pro",
    "GigaChat-3-Ultra",
)

app = FastAPI(title="Neuro Lab control plane", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
task_queue = redis.from_url(REDIS_URL, decode_responses=True)


class TaskRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    model: str
    credential_lane: Literal["primary", "freemium"]
    max_tokens: int = Field(default=512, ge=16, le=2048)


def read_first_line(path):
    try:
        return Path(path).read_text(encoding="utf-8").strip().splitlines()[0]
    except (FileNotFoundError, PermissionError, IndexError):
        return None


def host_metrics():
    load_text = read_first_line("/host/proc/loadavg")
    try:
        memory_text = Path("/host/proc/meminfo").read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError, OSError):
        memory_text = ""
    memory = {}
    for line in memory_text.splitlines():
        key, value = line.split(":", 1)
        memory[key] = int(value.strip().split()[0]) * 1024
    temperature = read_first_line("/host/sys/thermal_temp")
    disk = shutil.disk_usage("/srv/neuro-lab")
    return {
        "load_1m": float(load_text.split()[0]) if load_text else None,
        "memory_total": memory.get("MemTotal"),
        "memory_available": memory.get("MemAvailable"),
        "temperature_c": round(int(temperature) / 1000, 1) if temperature else None,
        "disk_total": disk.total,
        "disk_free": disk.free,
    }


def daily_lane_task_count(credential_lane):
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT count(*) FROM tasks
                   WHERE credential_lane=%s
                     AND created_at > now() - interval '24 hours'""",
                (credential_lane,),
            )
            return cur.fetchone()[0]


def record_queued_task(task_id, payload):
    """Persist the dashboard-visible queued state before delivery to Redis."""
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """INSERT INTO tasks (id, status, provider, model, credential_lane, request_ref)
               VALUES (%s, 'queued', %s, %s, %s, %s)
               ON CONFLICT (id) DO NOTHING""",
            (
                task_id,
                payload["provider"],
                payload["model"],
                payload["credential_lane"],
                payload["request_ref"],
            ),
        )
        conn.commit()


def record_enqueue_failure(task_id):
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            """UPDATE tasks SET status='failed', completed_at=now(),
               error_message='Task queue is unavailable before delivery'
               WHERE id=%s AND status='queued'""",
            (task_id,),
        )
        conn.commit()


def serialize_row(row):
    result = row[8] or {}
    return {
        "id": str(row[0]),
        "created_at": row[1].isoformat() if row[1] else None,
        "completed_at": row[2].isoformat() if row[2] else None,
        "status": row[3],
        "provider": row[4],
        "model": row[5],
        "request_ref": row[6],
        "error": row[7],
        "result": result,
    }


def overview():
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, created_at, completed_at, status, provider, model, request_ref,
                          error_message, result - 'embeddings'
                   FROM tasks ORDER BY created_at DESC LIMIT 18"""
            )
            recent = [serialize_row(row) for row in cur.fetchall()]
            cur.execute(
                """SELECT status, count(*) FROM tasks
                   WHERE created_at > now() - interval '24 hours'
                   GROUP BY status"""
            )
            task_counts = {status: count for status, count in cur.fetchall()}
            cur.execute(
                """SELECT COALESCE(sum(input_tokens), 0), COALESCE(sum(output_tokens), 0),
                          count(*)
                   FROM cost_events WHERE recorded_at > now() - interval '24 hours'"""
            )
            input_tokens, output_tokens, cost_events = cur.fetchone()
            cur.execute(
                """SELECT raw_usage->>'credential_lane', count(*)
                   FROM cost_events WHERE recorded_at > now() - interval '24 hours'
                   GROUP BY raw_usage->>'credential_lane'"""
            )
            lane_counts = {lane or "unknown": count for lane, count in cur.fetchall()}
            cur.execute(
                """SELECT count(*) FROM worker_heartbeats
                   WHERE last_seen > now() - interval '90 seconds'"""
            )
            active_workers = cur.fetchone()[0]
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "refresh_seconds": REFRESH_SECONDS,
        "host": host_metrics(),
        "queue_depth": task_queue.llen(TASK_QUEUE),
        "active_workers": active_workers,
        "tasks_24h": task_counts,
        "usage_24h": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "events": cost_events,
            "by_lane": lane_counts,
        },
        "recent_tasks": recent,
    }


@app.get("/")
def index():
    return FileResponse("static/index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/overview")
def get_overview():
    try:
        return overview()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Control-plane data is temporarily unavailable") from exc


@app.get("/api/models")
def get_models():
    return {"chat_models": CHAT_MODELS}


@app.get("/api/temperature")
def get_temperature(hours: int = 1):
    if hours not in (1, 12, 24):
        raise HTTPException(status_code=422, detail="hours must be 1, 12, or 24")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT recorded_at, temperature_c
                   FROM metric_samples
                   WHERE recorded_at >= now() - make_interval(hours => %s)
                   ORDER BY recorded_at""",
                (hours,),
            )
            samples = [
                {"recorded_at": recorded_at.isoformat(), "temperature_c": float(temperature_c)}
                for recorded_at, temperature_c in cur.fetchall()
            ]
    return {"hours": hours, "samples": samples}


@app.post("/api/tasks")
def create_task(request: TaskRequest):
    if request.model not in CHAT_MODELS:
        raise HTTPException(status_code=422, detail="Unsupported chat model")
    task_id = str(uuid.uuid4())
    payload = {
        "task_id": task_id,
        "provider": "gigachat",
        "operation": "chat",
        "credential_lane": request.credential_lane,
        "model": request.model,
        "messages": [{"role": "user", "content": request.prompt}],
        "max_tokens": request.max_tokens,
        "request_ref": f"dashboard-{int(time.time())}",
    }
    try:
        if task_queue.llen(TASK_QUEUE) >= MAX_QUEUE_DEPTH:
            raise HTTPException(status_code=429, detail="Task queue is at its safe capacity")
        if daily_lane_task_count(request.credential_lane) >= MAX_TASKS_PER_LANE_PER_DAY:
            raise HTTPException(status_code=429, detail="Credential lane reached its daily task budget")
        record_queued_task(task_id, payload)
        task_queue.rpush(TASK_QUEUE, json.dumps(payload, ensure_ascii=False))
    except redis.RedisError as exc:
        try:
            record_enqueue_failure(task_id)
        except psycopg.Error:
            pass
        raise HTTPException(status_code=503, detail="Task queue is unavailable") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Task state is unavailable") from exc
    return {"task_id": task_id, "status": "queued"}
