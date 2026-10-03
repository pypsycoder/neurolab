"""Single-document validated step artifacts; not a shared paid orchestrator."""
from hashlib import sha256
import json
from pathlib import Path

VERSION = "document-analysis-v2"


class AnalysisOutcomeUnknown(RuntimeError):
    """Do not repeat a possibly billed or invalid completed provider attempt."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def step_key(*, document_sha256, model_label, prompt):
    return sha256(canonical([VERSION, document_sha256, model_label,
                             sha256(prompt.encode()).hexdigest()]).encode()).hexdigest()


def run_cached_step(directory: Path, key: str, attempt: dict, ask, validate):
    """Reserve before SDK invocation; store only strict, bounded parsed output."""
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise ValueError("invalid analysis step key")
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / (key + ".lock")
    try:
        with lock.open("x", encoding="utf-8"):
            pass
    except FileExistsError:
        raise AnalysisOutcomeUnknown("analysis step locked; no automatic replay") from None
    try:
        return _run_cached_step(directory, key, attempt, ask, validate)
    finally:
        lock.unlink()


def _run_cached_step(directory: Path, key: str, attempt: dict, ask, validate):
    path = directory / (key + ".json")
    if path.is_symlink():
        raise ValueError("analysis cache symlink forbidden")
    if path.exists():
        if path.stat().st_size > 60000:
            raise ValueError("analysis cache oversized")
        entry = json.loads(path.read_text(encoding="utf-8"))
        if entry.get("step_key") != key or entry.get("version") != VERSION:
            raise ValueError("analysis cache identity mismatch")
        expected = {"version", "step_key", "status", "requests"}
        if entry.get("status") == "completed":
            expected |= {"validated_output", "output_sha256"}
        if set(entry) != expected or type(entry.get("requests")) is not int or not 1 <= entry["requests"] <= 2:
            raise ValueError("analysis cache shape mismatch")
        if entry.get("status") == "completed":
            raw = canonical(entry["validated_output"])
            if sha256(raw.encode()).hexdigest() != entry.get("output_sha256"):
                raise ValueError("analysis cache digest mismatch")
            result = validate(raw)
            attempt.update(status="reused", new_model_calls=0,
                           output_sha256=entry["output_sha256"])
            return result
        # Only a definite quota refusal can be retried once on another lane.
        # Unknown outcomes/contract failures/parallel inflight are not retried.
        if entry.get("status") != "quota_refused" or entry.get("requests", 0) >= 2:
            raise AnalysisOutcomeUnknown("analysis step cannot be repeated automatically")
        requests = entry["requests"] + 1
    else:
        requests = 1
    entry = {"version": VERSION, "step_key": key, "status": "inflight", "requests": requests}
    # The exact-key lock serializes initial attempts and quota recovery. This
    # local artifact guard is not account-wide paid budget coordination.
    if path.exists():
        path.write_text(canonical(entry), encoding="utf-8")
    else:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(canonical(entry))
    path.chmod(0o600)
    attempt["new_model_calls"] = 1
    try:
        raw = ask()
        result = validate(raw)
        # Re-serialization contains validated paraphrases only, no raw reply.
        if hasattr(result, "as_json"):
            clean = json.loads(result.as_json())
            # Card metadata is reintroduced from exact host receipt on reload.
            for field in ("source_key", "document_id", "document_sha256", "reviewer_status", "card_version"):
                clean.pop(field, None)
        else:
            from dataclasses import asdict
            clean = asdict(result)
            clean.pop("page_start", None)
            clean.pop("page_end", None)
        serial = canonical(clean)
        if len(serial.encode()) > 48000:
            raise ValueError("validated analysis output exceeds cache limit")
        entry.update(status="completed", validated_output=clean,
                     output_sha256=sha256(serial.encode()).hexdigest())
        attempt.update(status="completed", output_sha256=entry["output_sha256"])
        return result
    except Exception as error:
        response = getattr(error, "response", None)
        status = getattr(error, "status_code", None) or getattr(response, "status_code", None)
        quota = status == 429 or type(error).__name__ == "RateLimitError"
        entry["status"] = "quota_refused" if quota else "outcome_unknown"
        attempt["status"] = entry["status"]
        raise
    finally:
        path.write_text(canonical(entry), encoding="utf-8")
        path.chmod(0o600)
