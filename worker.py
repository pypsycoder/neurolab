"""Queue worker with isolated GigaChat primary and Freemium credential lanes."""
import json
import logging
import os
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import psycopg
import redis

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("neuro_lab.worker")

queue = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
db_url = os.environ["DATABASE_URL"]
poll_seconds = int(os.getenv("ORCHESTRATOR_POLL_SECONDS", "3"))


class ProviderError(RuntimeError):
    """Provider failure safe to store in task metadata; never includes credentials."""


class GigaChatClient:
    def __init__(self):
        self.base_url = os.getenv("GIGACHAT_BASE_URL", "https://api.giga.chat").rstrip("/")
        self.oauth_url = os.getenv("GIGACHAT_OAUTH_URL", f"{self.base_url}/api/v2/oauth")
        self.scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.default_model = os.getenv("GIGACHAT_MODEL", "GigaChat")
        self.tokens = {}

    def credential_for(self, lane):
        key_env = {
            "primary": os.getenv("GIGACHAT_PRIMARY_KEY_ENV", "GIGACHAT_KEY_A1"),
            "freemium": os.getenv("GIGACHAT_FREEMIUM_KEY_ENV", "GIGACHAT_KEY_L1"),
        }.get(lane)
        if not key_env:
            raise ProviderError(f"unsupported GigaChat lane: {lane}")
        credential = os.getenv(key_env)
        if not credential:
            raise ProviderError(f"GigaChat credential is not configured for lane: {lane}")
        return credential

    def access_token(self, lane):
        cached = self.tokens.get(lane)
        if cached and cached["expires_at"] > time.time() + 60:
            return cached["token"]
        request = Request(
            self.oauth_url,
            data=urlencode({"scope": self.scope}).encode(),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {self.credential_for(lane)}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                token_data = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ProviderError(f"GigaChat OAuth failed: {getattr(exc, 'code', type(exc).__name__)}") from exc
        token = token_data.get("access_token")
        if not token:
            raise ProviderError("GigaChat OAuth response has no access token")
        self.tokens[lane] = {"token": token, "expires_at": float(token_data.get("expires_at", 0))}
        return token

    def complete(self, task):
        lane = task.get("credential_lane", "primary")
        messages = task.get("messages")
        if not isinstance(messages, list) or not messages:
            raise ProviderError("GigaChat task requires a non-empty messages array")
        body = {
            "model": task.get("model", self.default_model),
            "messages": messages,
            "stream": False,
        }
        for field in ("temperature", "max_tokens", "top_p"):
            if field in task:
                body[field] = task[field]
        request = Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode(),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.access_token(lane)}",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise ProviderError(f"GigaChat completion failed: {getattr(exc, 'code', type(exc).__name__)}") from exc
        choices = payload.get("choices") or []
        if not choices:
            raise ProviderError("GigaChat response has no choices")
        message = choices[0].get("message", {})
        return {
            "model": payload.get("model", body["model"]),
            "content": message.get("content"),
            "finish_reason": choices[0].get("finish_reason"),
            "usage": payload.get("usage", {}),
            "credential_lane": lane,
        }


gigachat = GigaChatClient()


def record_task(task_id, payload):
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO tasks (id, status, started_at, provider, model, request_ref)
                   VALUES (%s, 'running', now(), %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET status='running', started_at=now(), error_message=NULL""",
                (task_id, payload.get("provider"), payload.get("model"), payload.get("request_ref")),
            )
            conn.commit()


def record_succeeded(task_id, result):
    with psycopg.connect(db_url) as conn:
        conn.execute(
            "UPDATE tasks SET status='succeeded', completed_at=now(), result=%s WHERE id=%s",
            (json.dumps(result), task_id),
        )
        conn.commit()


def record_cost(task_id, provider, model, usage, credential_lane=None, amount_usd=None):
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO cost_events
                   (task_id, provider, model, input_tokens, output_tokens, amount_usd, raw_usage)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (task_id, provider, model,
                 usage.get("prompt_tokens", usage.get("input_tokens")),
                 usage.get("completion_tokens", usage.get("output_tokens")),
                 amount_usd, json.dumps({"usage": usage, "credential_lane": credential_lane})),
            )
            conn.commit()


def ensure_schema():
    with psycopg.connect(db_url) as conn:
        conn.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS result JSONB")
        conn.commit()


ensure_schema()


while True:
    item = queue.blpop("neuro-lab:tasks", timeout=poll_seconds)
    if item is None:
        continue
    _, raw_payload = item
    payload = json.loads(raw_payload)
    task_id = payload.get("task_id") or str(uuid.uuid4())
    try:
        record_task(task_id, payload)
        if payload.get("provider") == "gigachat":
            result = gigachat.complete(payload)
            record_succeeded(task_id, result)
            record_cost(task_id, "gigachat", result["model"], result["usage"], result["credential_lane"])
        elif payload.get("provider") == "local-smoke-test":
            result = {"model": payload.get("model"), "content": None, "credential_lane": "local"}
            record_succeeded(task_id, result)
            record_cost(task_id, "local-smoke-test", payload.get("model"), payload.get("usage", {}), "local", payload.get("amount_usd", 0))
        else:
            raise ProviderError(f"unsupported provider: {payload.get('provider')}")
        log.info("recorded task %s", task_id)
    except Exception:
        log.exception("failed task %s", task_id)
        with psycopg.connect(db_url) as conn:
            conn.execute("UPDATE tasks SET status='failed', completed_at=now() WHERE id=%s", (task_id,))
            conn.commit()
