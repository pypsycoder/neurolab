"""Enqueue one minimal request per GigaChat model and print a compact report."""
import argparse
import json
import os
import time
import uuid

import psycopg
import redis


CHAT_MODELS = (
    "GigaChat-2",
    "GigaChat-2-Max",
    "GigaChat-2-Pro",
    "GigaChat-3-Lightning",
    "GigaChat-3-Pro",
    "GigaChat-3-Ultra",
)
EMBEDDING_MODELS = (
    "Embeddings",
    "Embeddings-2",
    "EmbeddingsGigaR",
    "GigaEmbeddings-3B-2025-09",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", choices=("primary", "freemium"), default="primary")
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    all_models = (*CHAT_MODELS, *EMBEDDING_MODELS)
    selected = set(args.models or all_models)
    unknown = selected.difference(all_models)
    if unknown:
        raise SystemExit(f"Unknown model(s): {', '.join(sorted(unknown))}")

    run_ref = f"model-probe-{args.lane}-{int(time.time())}"
    task_queue = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    tasks = []
    for model in all_models:
        if model not in selected:
            continue
        task_id = str(uuid.uuid4())
        operation = "chat" if model in CHAT_MODELS else "embeddings"
        payload = {
            "task_id": task_id,
            "provider": "gigachat",
            "operation": operation,
            "credential_lane": args.lane,
            "model": model,
            "request_ref": f"{run_ref}:{model}",
        }
        if operation == "chat":
            payload.update({
                "messages": [{"role": "user", "content": "Ответь только OK"}],
                "max_tokens": 4,
                "temperature": 0.1,
            })
        else:
            payload["input"] = "тест"
        tasks.append((task_id, model, operation))
        task_queue.rpush("neuro-lab:tasks", json.dumps(payload, ensure_ascii=False))

    deadline = time.time() + args.timeout
    rows = {}
    while time.time() < deadline:
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, status, model, result, error_message FROM tasks WHERE id = ANY(%s)",
                    ([task_id for task_id, _, _ in tasks],),
                )
                rows = {str(row[0]): row for row in cur.fetchall()}
        if len(rows) == len(tasks) and all(
            row[1] in ("succeeded", "failed") for row in rows.values()
        ):
            break
        time.sleep(2)

    report = []
    for task_id, requested_model, operation in tasks:
        row = rows.get(task_id)
        if row is None:
            report.append({
                "requested_model": requested_model,
                "operation": operation,
                "status": "timeout",
            })
            continue
        result = row[3] or {}
        item = {
            "requested_model": requested_model,
            "returned_model": row[2],
            "operation": operation,
            "status": row[1],
            "credential_lane": args.lane,
        }
        if row[1] == "succeeded":
            item["usage"] = result.get("usage", {})
            if operation == "chat":
                item["content"] = result.get("content")
            else:
                item["dimensions"] = result.get("dimensions")
        else:
            item["error"] = row[4]
        report.append(item)

    print(json.dumps({"run_ref": run_ref, "results": report}, ensure_ascii=False, indent=2))
    if any(item["status"] != "succeeded" for item in report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
