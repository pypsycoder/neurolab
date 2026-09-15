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
VALID_CREDENTIAL_LANES = frozenset({"primary", "freemium"})
TASK_LEASE_SECONDS = max(180, int(os.getenv("ORCHESTRATOR_TASK_LEASE_SECONDS", "900")))
RECOVERY_INTERVAL_SECONDS = max(
    15, int(os.getenv("ORCHESTRATOR_RECOVERY_INTERVAL_SECONDS", "60"))
)
# A dashboard process can theoretically stop after committing the task row but
# before RPUSH.  Do not treat a brief queue delay as an orphan: this is only a
# bounded repair for rows that have been absent from both durable Redis lists
# for a long time.  The dispatch outbox below is the primary repair path;
# this reaper remains a bounded safeguard for legacy or manually-created rows.
ORPHANED_QUEUED_SECONDS = max(
    300, int(os.getenv("ORCHESTRATOR_ORPHANED_QUEUED_SECONDS", "1800"))
)
OUTBOX_DISPATCH_INTERVAL_SECONDS = max(
    1, int(os.getenv("ORCHESTRATOR_OUTBOX_DISPATCH_INTERVAL_SECONDS", "3"))
)
OUTBOX_CLAIM_SECONDS = max(
    30, int(os.getenv("ORCHESTRATOR_OUTBOX_CLAIM_SECONDS", "90"))
)
OUTBOX_BATCH_SIZE = max(1, int(os.getenv("ORCHESTRATOR_OUTBOX_BATCH_SIZE", "16")))


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


def validate_payload(payload, *, require_task_id=False):
    """Validate queue fields that would otherwise poison PostgreSQL recovery."""
    if not isinstance(payload, dict):
        raise ValueError("task payload must be an object")
    lane = payload.get("credential_lane")
    if lane is not None and lane not in VALID_CREDENTIAL_LANES:
        raise ValueError("task payload has an unsupported credential lane")
    if not require_task_id:
        return None
    return str(uuid.UUID(str(payload["task_id"])))


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


def claim_task(task_id, payload):
    """Atomically claim a queued task and return its execution lease ID.

    A duplicate delivery is acknowledged without a second provider call.  A
    task whose worker dies can later be returned to ``queued`` only after its
    execution lease expires.
    """
    execution_id = str(uuid.uuid4())
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO tasks (id, status, provider, model, credential_lane, request_ref)
                   VALUES (%s, 'queued', %s, %s, %s, %s)
                   ON CONFLICT (id) DO NOTHING""",
                (
                    task_id,
                    payload.get("provider"),
                    payload.get("model"),
                    payload.get("credential_lane"),
                    payload.get("request_ref"),
                ),
            )
            cur.execute(
                """UPDATE tasks
                   SET status='running', started_at=now(), completed_at=NULL,
                       error_message=NULL, execution_id=%s
                   WHERE id=%s AND status='queued'
                   RETURNING execution_id""",
                (execution_id, task_id),
            )
            row = cur.fetchone()
            conn.commit()
    return str(row[0]) if row else None


def record_succeeded(task_id, execution_id, result):
    with psycopg.connect(db_url) as conn:
        cursor = conn.execute(
            """UPDATE tasks
               SET status='succeeded', completed_at=now(), model=COALESCE(%s, model), result=%s
               WHERE id=%s AND status='running' AND execution_id=%s""",
            (result.get("model"), json.dumps(result), task_id, execution_id),
        )
        conn.commit()
    return cursor.rowcount == 1


def record_failed(task_id, execution_id, exc):
    with psycopg.connect(db_url) as conn:
        cursor = conn.execute(
            """UPDATE tasks SET status='failed', completed_at=now(), error_message=%s
               WHERE id=%s AND status='running' AND execution_id=%s""",
            (safe_error_message(exc), task_id, execution_id),
        )
        conn.commit()
    return cursor.rowcount == 1


def record_cost(task_id, execution_id, provider, model, usage, credential_lane=None, amount_usd=None):
    """Persist one cost receipt for one concrete provider execution lease."""
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO cost_events
                   (task_id, execution_id, provider, model, input_tokens, output_tokens, amount_usd, raw_usage)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (task_id, execution_id)
                   WHERE task_id IS NOT NULL AND execution_id IS NOT NULL DO NOTHING""",
                (task_id, execution_id, provider, model,
                 usage.get("prompt_tokens", usage.get("input_tokens", usage.get("total_tokens"))),
                 usage.get("completion_tokens", usage.get("output_tokens", 0)),
                 amount_usd, json.dumps({"usage": usage, "credential_lane": credential_lane})),
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


def claim_pending_outbox():
    """Claim a bounded batch of undelivered dashboard requests.

    A crash before Redis acknowledgement merely lets the short-lived claim
    expire.  A crash after RPUSH can create a duplicate delivery, which is
    safe because ``claim_task`` is the single provider-execution gate.
    """
    delivery_claim_id = str(uuid.uuid4())
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """WITH candidates AS (
                       SELECT outbox.task_id
                       FROM task_outbox AS outbox
                       JOIN tasks ON tasks.id = outbox.task_id
                       WHERE outbox.delivered_at IS NULL
                         AND tasks.status='queued'
                         AND (
                             outbox.delivery_claimed_at IS NULL OR
                             outbox.delivery_claimed_at < now() - make_interval(secs => %s)
                         )
                       ORDER BY outbox.created_at
                       FOR UPDATE OF outbox SKIP LOCKED
                       LIMIT %s
                   )
                   UPDATE task_outbox AS outbox
                   SET delivery_claim_id=%s,
                       delivery_claimed_at=now(),
                       delivery_attempts=outbox.delivery_attempts + 1,
                       last_error=NULL
                   FROM candidates
                   WHERE outbox.task_id=candidates.task_id
                   RETURNING outbox.task_id, outbox.payload, outbox.delivery_claim_id""",
                (OUTBOX_CLAIM_SECONDS, OUTBOX_BATCH_SIZE, delivery_claim_id),
            )
            claimed = cur.fetchall()
            conn.commit()
    return [(str(task_id), payload, str(claim_id)) for task_id, payload, claim_id in claimed]


def mark_outbox_delivered(task_id, delivery_claim_id):
    with psycopg.connect(db_url) as conn:
        cursor = conn.execute(
            """UPDATE task_outbox
               SET delivered_at=now(), delivery_claim_id=NULL, delivery_claimed_at=NULL,
                   last_error=NULL
               WHERE task_id=%s AND delivered_at IS NULL AND delivery_claim_id=%s""",
            (task_id, delivery_claim_id),
        )
        conn.commit()
    return cursor.rowcount == 1


def record_outbox_delivery_error(task_id, delivery_claim_id, exc):
    """Retain the claim until expiry; a healthy worker must not hot-loop Redis."""
    with psycopg.connect(db_url) as conn:
        conn.execute(
            """UPDATE task_outbox
               SET last_error=%s
               WHERE task_id=%s AND delivered_at IS NULL AND delivery_claim_id=%s""",
            (f"delivery error: {type(exc).__name__}", task_id, delivery_claim_id),
        )
        conn.commit()


def publish_outbox_claim(task_id, payload, delivery_claim_id):
    """Publish one verified outbox row, then acknowledge its DB delivery claim."""
    validated_task_id = validate_payload(payload, require_task_id=True)
    if validated_task_id != task_id:
        raise ValueError("outbox task ID does not match payload task ID")
    task_queue_payload = json.dumps(payload, ensure_ascii=False)
    queue.rpush(TASK_QUEUE, task_queue_payload)
    return mark_outbox_delivered(task_id, delivery_claim_id)


def dispatch_pending_outbox():
    """Deliver committed dashboard requests without relying on dashboard uptime."""
    try:
        claimed = claim_pending_outbox()
    except psycopg.Error as exc:
        log.warning("outbox claim failed (%s)", type(exc).__name__)
        return
    for task_id, payload, delivery_claim_id in claimed:
        try:
            if publish_outbox_claim(task_id, payload, delivery_claim_id):
                log.info("delivered outbox task %s", task_id)
        except (redis.RedisError, psycopg.Error, TypeError, ValueError, json.JSONDecodeError) as exc:
            log.warning("outbox delivery retained for task %s (%s)", task_id, type(exc).__name__)
            try:
                record_outbox_delivery_error(task_id, delivery_claim_id, exc)
            except psycopg.Error:
                log.warning("could not record outbox delivery error for task %s", task_id)


def requeue_stale_delivery(raw_payload):
    """Move one exact processing item back to the queue in one Redis script."""
    return queue.eval(
        """if redis.call('LREM', KEYS[1], 1, ARGV[1]) == 1 then
              redis.call('LPUSH', KEYS[2], ARGV[1])
              return 1
            end
            return 0""",
        2,
        PROCESSING_QUEUE,
        TASK_QUEUE,
        raw_payload,
    )


def dead_letter_processing_delivery(raw_payload):
    """Atomically remove an invalid processing delivery into dead-letter."""
    return queue.eval(
        """if redis.call('LREM', KEYS[1], 1, ARGV[1]) == 1 then
              redis.call('RPUSH', KEYS[2], ARGV[1])
              return 1
            end
            return 0""",
        2,
        PROCESSING_QUEUE,
        DEAD_LETTER_QUEUE,
        raw_payload,
    )


def acknowledge_processing_delivery(raw_payload):
    """Remove a persisted terminal delivery left by a worker crash."""
    return queue.lrem(PROCESSING_QUEUE, 1, raw_payload)


def delivery_task_ids():
    """Return valid task IDs currently observed in either durable Redis list.

    Malformed entries intentionally do not protect a task row: normal recovery
    will move those entries to dead-letter instead of executing them.
    """
    task_ids = set()
    for queue_name in (TASK_QUEUE, PROCESSING_QUEUE):
        for raw_payload in queue.lrange(queue_name, 0, -1):
            try:
                payload = json.loads(raw_payload)
                task_ids.add(validate_payload(payload, require_task_id=True))
            except (TypeError, KeyError, ValueError, json.JSONDecodeError):
                continue
    return task_ids


def reap_orphaned_queued_tasks():
    """Fail long-lived queued rows whose raw delivery is absent from Redis.

    This deliberately does not reconstruct or requeue a request because prompt
    content is not stored in PostgreSQL.  The bounded repair makes a failed
    dispatch visible and allows the user to submit a fresh request.
    """
    try:
        observed_task_ids = delivery_task_ids()
    except redis.RedisError as exc:
        log.warning("could not inspect delivery queues for queued reaper (%s)", type(exc).__name__)
        return
    try:
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id FROM tasks
                       WHERE status='queued'
                         AND created_at < now() - make_interval(secs => %s)""",
                    (ORPHANED_QUEUED_SECONDS,),
                )
                candidates = [str(row[0]) for row in cur.fetchall()]
                for task_id in candidates:
                    if task_id in observed_task_ids:
                        continue
                    cur.execute(
                        """UPDATE tasks
                           SET status='failed', completed_at=now(),
                               error_message='Task delivery was not observed before queue timeout'
                           WHERE id=%s AND status='queued'
                             AND created_at < now() - make_interval(secs => %s)""",
                        (task_id, ORPHANED_QUEUED_SECONDS),
                    )
                    if cur.rowcount == 1:
                        log.warning("marked orphaned queued task as failed %s", task_id)
                conn.commit()
    except psycopg.Error as exc:
        log.warning("queued-task reaper failed (%s)", type(exc).__name__)


def recover_stale_deliveries():
    """Recover processing deliveries without duplicating a provider call.

    A worker can die after Redis moves a raw message into ``processing`` but
    before it claims the PostgreSQL row.  Such a delivery has no lease to age.
    It is safe to create/requeue a ``queued`` row: a later simultaneous claim
    is atomic and therefore cannot result in a second provider invocation.
    """
    for raw_payload in queue.lrange(PROCESSING_QUEUE, 0, -1):
        try:
            payload = json.loads(raw_payload)
            task_id = validate_payload(payload, require_task_id=True)
        except (TypeError, KeyError, ValueError, json.JSONDecodeError):
            if dead_letter_processing_delivery(raw_payload):
                log.warning("moved malformed processing payload to dead-letter queue")
            continue
        try:
            with psycopg.connect(db_url) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO tasks (id, status, provider, model, credential_lane, request_ref)
                           VALUES (%s, 'queued', %s, %s, %s, %s)
                           ON CONFLICT (id) DO NOTHING
                           RETURNING id""",
                        (
                            task_id,
                            payload.get("provider"),
                            payload.get("model"),
                            payload.get("credential_lane"),
                            payload.get("request_ref"),
                        ),
                    )
                    recovered = cur.fetchone() is not None
                    if not recovered:
                        cur.execute(
                            """UPDATE tasks
                               SET status='queued', started_at=NULL, execution_id=NULL
                               WHERE id=%s AND (
                                   status='queued' OR
                                   (status='running' AND started_at < now() - make_interval(secs => %s))
                               )
                               RETURNING id""",
                            (task_id, TASK_LEASE_SECONDS),
                        )
                        recovered = cur.fetchone() is not None
                    terminal = False
                    if not recovered:
                        cur.execute("SELECT status FROM tasks WHERE id=%s", (task_id,))
                        status_row = cur.fetchone()
                        terminal = bool(status_row and status_row[0] in {"succeeded", "failed"})
                    conn.commit()
        except psycopg.Error as exc:
            log.warning(
                "could not inspect processing delivery %s (%s); continuing recovery",
                task_id,
                type(exc).__name__,
            )
            continue
        try:
            if recovered and requeue_stale_delivery(raw_payload):
                log.warning("requeued recoverable processing delivery %s", task_id)
            elif terminal and acknowledge_processing_delivery(raw_payload):
                log.info("acknowledged persisted terminal delivery %s", task_id)
        except redis.RedisError as exc:
            log.warning("could not update processing delivery %s (%s)", task_id, type(exc).__name__)


def handle_delivery(raw_payload):
    """Handle one durable Redis delivery.

    The caller acknowledges the processing-list entry only after this returns
    ``True``.  A database outage therefore leaves the original message in the
    processing list instead of silently deleting it.
    """
    try:
        payload = json.loads(raw_payload)
        validate_payload(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        queue.rpush(DEAD_LETTER_QUEUE, raw_payload)
        log.warning("moved malformed task payload to dead-letter queue")
        return True

    task_id = payload.get("task_id") or str(uuid.uuid4())
    execution_id = None
    try:
        heartbeat("running")
        execution_id = claim_task(task_id, payload)
        if execution_id is None:
            log.info("acknowledging duplicate or already-final task %s", task_id)
            return True
        if payload.get("provider") == "gigachat":
            operation = payload.get("operation", "chat")
            if operation == "chat":
                result = gigachat.complete(payload)
            elif operation in ("embedding", "embeddings"):
                result = gigachat.embed(payload)
            else:
                raise ProviderError(f"unsupported GigaChat operation: {operation}")
            # The provider response is a real external spend even if the task
            # status update later loses its lease race.  Receipt uniqueness is
            # scoped to this execution lease, so a retry cannot double-count it.
            record_cost(task_id, execution_id, "gigachat", result["model"], result["usage"], result["credential_lane"])
            record_succeeded(task_id, execution_id, result)
        elif payload.get("provider") == "local-smoke-test":
            result = {"model": payload.get("model"), "content": None, "credential_lane": "local"}
            record_cost(task_id, execution_id, "local-smoke-test", payload.get("model"), payload.get("usage", {}), "local", payload.get("amount_usd", 0))
            record_succeeded(task_id, execution_id, result)
        else:
            raise ProviderError(f"unsupported provider: {payload.get('provider')}")
        log.info("recorded task %s", task_id)
    except Exception as exc:
        # Do not emit an arbitrary exception string: driver errors can contain
        # connection URLs.  The database receives the same safe summary.
        log.error("failed task %s: %s", task_id, safe_error_message(exc))
        try:
            if execution_id is None:
                raise RuntimeError("task was not claimed")
            record_failed(task_id, execution_id, exc)
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
    last_recovery_at = 0.0
    last_outbox_dispatch_at = 0.0
    while True:
        if time.monotonic() - last_outbox_dispatch_at >= OUTBOX_DISPATCH_INTERVAL_SECONDS:
            dispatch_pending_outbox()
            last_outbox_dispatch_at = time.monotonic()
        if time.monotonic() - last_recovery_at >= RECOVERY_INTERVAL_SECONDS:
            try:
                recover_stale_deliveries()
            except Exception:
                log.error("processing-queue recovery failed; deliveries retained")
            try:
                reap_orphaned_queued_tasks()
            except Exception:
                log.error("queued-task reaper failed; queued rows retained")
            last_recovery_at = time.monotonic()
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
