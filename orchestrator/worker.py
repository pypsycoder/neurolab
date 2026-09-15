"""Queue worker with isolated GigaChat primary and Freemium credential lanes."""
import json
import logging
import os
import socket
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
retry_attempts = int(os.getenv("GIGACHAT_RETRY_ATTEMPTS", "5"))
worker_name = socket.gethostname()
last_heartbeat_at = 0.0
TASK_QUEUE = "neuro-lab:tasks"
PROCESSING_QUEUE = "neuro-lab:tasks:processing"
DEAD_LETTER_QUEUE = "neuro-lab:tasks:dead"


class ProviderError(RuntimeError):
    """Provider failure safe to store in task metadata; never includes credentials."""

    def __init__(self, message, *, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def normalize_expiry_timestamp(value):
    """Normalise provider expiration timestamps to Unix seconds.

    GigaChat OAuth has returned both ``expires_at`` in milliseconds and
    ``exp`` in seconds.  Keeping the worker cache in one unit prevents a
    permanently stale bearer token after its short-lived provider lifetime.
    """
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return 0.0
    return timestamp / 1000 if timestamp > 100_000_000_000 else timestamp


def safe_error_message(exc):
    """Return an error safe for the database and dashboard.

    Only provider errors are deliberately constructed without credentials.
    Other exception strings can contain connection URLs or implementation
    details, so preserve only their class name outside the container log.
    """
    if isinstance(exc, ProviderError):
        return str(exc)[:1000]
    return f"internal error: {type(exc).__name__}"


class GigaChatClient:
    def __init__(self):
        self.base_url = os.getenv("GIGACHAT_BASE_URL", "https://api.giga.chat").rstrip("/")
        self.oauth_url = os.getenv(
            "GIGACHAT_OAUTH_URL",
            "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        )
        self.scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.default_model = os.getenv("GIGACHAT_MODEL", "GigaChat-2-Pro")
        self.default_embedding_model = os.getenv(
            "GIGACHAT_EMBEDDING_MODEL",
            "GigaEmbeddings-3B-2025-09",
        )
        self.tokens = {}

    @staticmethod
    def request_json(request, label, timeout):
        for attempt in range(retry_attempts):
            try:
                with urlopen(request, timeout=timeout) as response:
                    return json.load(response)
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if retryable and attempt + 1 < retry_attempts:
                    retry_after = exc.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else 2 ** attempt
                    except ValueError:
                        delay = 2 ** attempt
                    delay = min(max(delay, 1), 30)
                    log.warning("%s returned %s; retrying in %.0fs", label, exc.code, delay)
                    time.sleep(delay)
                    continue
                raise ProviderError(f"{label} failed: {exc.code}", status_code=exc.code) from exc
            except (URLError, TimeoutError) as exc:
                if attempt + 1 < retry_attempts:
                    delay = min(2 ** attempt, 30)
                    log.warning("%s failed temporarily; retrying in %ss", label, delay)
                    time.sleep(delay)
                    continue
                raise ProviderError(f"{label} failed: {type(exc).__name__}") from exc
        raise ProviderError(f"{label} failed after retries")

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
        token_data = self.request_json(request, "GigaChat OAuth", 30)
        token = token_data.get("access_token")
        if not token:
            raise ProviderError("GigaChat OAuth response has no access token")
        expires_at = normalize_expiry_timestamp(
            token_data.get("expires_at") or token_data.get("exp")
        )
        if expires_at <= time.time() + 60:
            raise ProviderError("GigaChat OAuth response has expired or invalid expiration")
        self.tokens[lane] = {"token": token, "expires_at": expires_at}
        return token

    def authorized_request_json(self, lane, request_factory, label, timeout):
        """Issue a bearer request and refresh one rejected cached token."""
        for attempt in range(2):
            request = request_factory(self.access_token(lane))
            try:
                return self.request_json(request, label, timeout)
            except ProviderError as exc:
                if exc.status_code != 401 or attempt:
                    raise
                self.tokens.pop(lane, None)
                log.info("%s rejected cached GigaChat token; refreshing once", label)
        raise ProviderError(f"{label} failed after token refresh")

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
        def request_factory(token):
            return Request(
                f"{self.base_url}/v1/chat/completions",
                data=json.dumps(body, ensure_ascii=False).encode(),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )

        payload = self.authorized_request_json(
            lane, request_factory, "GigaChat completion", 120
        )
        choices = payload.get("choices") or []
        if not choices:
            raise ProviderError("GigaChat response has no choices")
        message = choices[0].get("message", {})
        return {
            "model": payload.get("model", body["model"]),
            "operation": "chat",
            "content": message.get("content"),
            "finish_reason": choices[0].get("finish_reason"),
            "usage": payload.get("usage", {}),
            "credential_lane": lane,
        }

    def embed(self, task):
        lane = task.get("credential_lane", "primary")
        input_value = task.get("input")
        valid_list = isinstance(input_value, list) and input_value and all(
            isinstance(item, str) and item for item in input_value
        )
        if not (isinstance(input_value, str) and input_value) and not valid_list:
            raise ProviderError("GigaChat embeddings task requires non-empty string input or string array")
        body = {
            "model": task.get("model", self.default_embedding_model),
            "input": input_value,
        }
        def request_factory(token):
            return Request(
                f"{self.base_url}/v1/embeddings",
                data=json.dumps(body, ensure_ascii=False).encode(),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )

        payload = self.authorized_request_json(
            lane, request_factory, "GigaChat embeddings", 120
        )
        embeddings = payload.get("data") or []
        if not embeddings:
            raise ProviderError("GigaChat embeddings response has no data")
        return {
            "model": payload.get("model", body["model"]),
            "operation": "embeddings",
            "embeddings": [
                {"index": item.get("index"), "embedding": item.get("embedding", [])}
                for item in embeddings
            ],
            "dimensions": [len(item.get("embedding", [])) for item in embeddings],
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
            """UPDATE tasks
               SET status='succeeded', completed_at=now(), model=COALESCE(%s, model), result=%s
               WHERE id=%s""",
            (result.get("model"), json.dumps(result), task_id),
        )
        conn.commit()


def record_failed(task_id, exc):
    with psycopg.connect(db_url) as conn:
        conn.execute(
            "UPDATE tasks SET status='failed', completed_at=now(), error_message=%s WHERE id=%s",
            (safe_error_message(exc), task_id),
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
                 usage.get("prompt_tokens", usage.get("input_tokens", usage.get("total_tokens"))),
                 usage.get("completion_tokens", usage.get("output_tokens", 0)),
                 amount_usd, json.dumps({"usage": usage, "credential_lane": credential_lane})),
            )
            conn.commit()


def ensure_schema():
    with psycopg.connect(db_url) as conn:
        conn.execute("ALTER TABLE tasks ADD COLUMN IF NOT EXISTS result JSONB")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS worker_heartbeats (
                   worker_name TEXT PRIMARY KEY,
                   last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
                   status TEXT NOT NULL DEFAULT 'idle'
               )"""
        )
        conn.commit()


def heartbeat(status):
    global last_heartbeat_at
    if status == "idle" and time.time() - last_heartbeat_at < 30:
        return
    try:
        with psycopg.connect(db_url) as conn:
            conn.execute(
                """INSERT INTO worker_heartbeats (worker_name, last_seen, status)
                   VALUES (%s, now(), %s)
                   ON CONFLICT (worker_name)
                   DO UPDATE SET last_seen=EXCLUDED.last_seen, status=EXCLUDED.status""",
                (worker_name, status),
            )
            conn.commit()
        last_heartbeat_at = time.time()
    except Exception:
        log.warning("worker heartbeat failed", exc_info=True)


def handle_delivery(raw_payload):
    """Handle one durable Redis delivery.

    The caller acknowledges the processing-list entry only after this returns
    ``True``.  A database outage therefore leaves the original message in the
    processing list instead of silently deleting it.
    """
    try:
        payload = json.loads(raw_payload)
        if not isinstance(payload, dict):
            raise ValueError("task payload must be an object")
    except (TypeError, ValueError, json.JSONDecodeError):
        queue.rpush(DEAD_LETTER_QUEUE, raw_payload)
        log.warning("moved malformed task payload to dead-letter queue")
        return True

    task_id = payload.get("task_id") or str(uuid.uuid4())
    try:
        heartbeat("running")
        record_task(task_id, payload)
        if payload.get("provider") == "gigachat":
            operation = payload.get("operation", "chat")
            if operation == "chat":
                result = gigachat.complete(payload)
            elif operation in ("embedding", "embeddings"):
                result = gigachat.embed(payload)
            else:
                raise ProviderError(f"unsupported GigaChat operation: {operation}")
            record_succeeded(task_id, result)
            record_cost(task_id, "gigachat", result["model"], result["usage"], result["credential_lane"])
        elif payload.get("provider") == "local-smoke-test":
            result = {"model": payload.get("model"), "content": None, "credential_lane": "local"}
            record_succeeded(task_id, result)
            record_cost(task_id, "local-smoke-test", payload.get("model"), payload.get("usage", {}), "local", payload.get("amount_usd", 0))
        else:
            raise ProviderError(f"unsupported provider: {payload.get('provider')}")
        log.info("recorded task %s", task_id)
    except Exception as exc:
        # Do not emit an arbitrary exception string: driver errors can contain
        # connection URLs.  The database receives the same safe summary.
        log.error("failed task %s: %s", task_id, safe_error_message(exc))
        try:
            record_failed(task_id, exc)
        except Exception:
            log.error(
                "could not persist failure for task %s; retaining delivery (%s)",
                task_id,
                type(exc).__name__,
            )
            return False
        return True
    finally:
        heartbeat("idle")
    return True


def run_worker():
    ensure_schema()
    while True:
        heartbeat("idle")
        raw_payload = queue.blmove(
            TASK_QUEUE,
            PROCESSING_QUEUE,
            timeout=poll_seconds,
            src="LEFT",
            dest="RIGHT",
        )
        if raw_payload is None:
            continue
        if handle_delivery(raw_payload):
            queue.lrem(PROCESSING_QUEUE, 1, raw_payload)


if __name__ == "__main__":
    run_worker()
