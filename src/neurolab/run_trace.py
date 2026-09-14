"""Redacted, deterministic metadata trace for synthetic NeuroLab runs."""

from dataclasses import dataclass
from hashlib import sha256
import re


class RunTracePolicyError(ValueError):
    """Synthetic run trace contains invalid or potentially sensitive metadata."""


@dataclass(frozen=True)
class SyntheticRunTrace:
    """Metadata only: no prompt, model output, source content, path, or secret values."""

    run_id: str
    graph_version: str
    prompt_version: str
    decision: str
    latency_ms: int
    audit: tuple[str, ...]
    artifact_refs: tuple[str, ...]


_VERSION = re.compile(r"^v[0-9]+(?:\.[0-9]+){0,2}$")
_LABEL = re.compile(r"^[a-z][a-z0-9:_-]{2,127}$")
_ARTIFACT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_DECISIONS = frozenset({"review_required", "blocked", "cancelled"})


def _deterministic_run_id(thread_id: str) -> str:
    if not isinstance(thread_id, str) or not thread_id.strip() or len(thread_id) > 256:
        raise RunTracePolicyError("thread id is invalid")
    return sha256(f"neurolab-synthetic:{thread_id}".encode("utf-8")).hexdigest()


def require_safe_run_trace(trace: SyntheticRunTrace) -> None:
    """Validate only redacted labels, bounded metrics, and relative artifact references."""
    if not re.fullmatch(r"[0-9a-f]{64}", trace.run_id):
        raise RunTracePolicyError("run id is malformed")
    if not _VERSION.fullmatch(trace.graph_version) or not _VERSION.fullmatch(trace.prompt_version):
        raise RunTracePolicyError("version label is malformed")
    if trace.decision not in _DECISIONS:
        raise RunTracePolicyError("trace decision is not allowed")
    if not isinstance(trace.latency_ms, int) or isinstance(trace.latency_ms, bool) or trace.latency_ms < 0:
        raise RunTracePolicyError("trace latency is invalid")
    if not trace.audit or any(not _LABEL.fullmatch(item) for item in trace.audit):
        raise RunTracePolicyError("trace audit must contain safe labels")
    if any(
        not _ARTIFACT.fullmatch(item)
        or item.startswith("/")
        or ".." in item.split("/")
        for item in trace.artifact_refs
    ):
        raise RunTracePolicyError("artifact reference is unsafe")


def build_synthetic_run_trace(
    *, thread_id: str, decision: str, latency_ms: int, audit: tuple[str, ...]
) -> SyntheticRunTrace:
    """Build and validate a deterministic, metadata-only synthetic run trace."""
    trace = SyntheticRunTrace(
        run_id=_deterministic_run_id(thread_id),
        graph_version="v1",
        prompt_version="v1",
        decision=decision,
        latency_ms=latency_ms,
        audit=audit,
        artifact_refs=("docs/integrations/ARCHITECTURE_SMOKE.md",),
    )
    require_safe_run_trace(trace)
    return trace
