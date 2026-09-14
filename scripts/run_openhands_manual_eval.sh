#!/usr/bin/env bash
# Run one approval-gated OpenHands evaluation against a disposable synthetic repo.
# This is intentionally separate from the automated smoke runner.
set -euo pipefail

if [[ "${RUN_OPENHANDS_MANUAL_EVAL:-0}" != "1" ]]; then
  echo "Set RUN_OPENHANDS_MANUAL_EVAL=1 for this one manual synthetic evaluation." >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
RUNTIME_ROOT="$PROJECT_ROOT/runtime"
FIXTURE_ROOT="$PROJECT_ROOT/tests/fixtures/synthetic-worktree"
OPENHANDS_BINARY="${OPENHANDS_BINARY:-$PROJECT_ROOT/runtime/openhands-eval/bin/openhands-1.16.0-linux-arm64}"
EVAL_IMAGE="${OPENHANDS_EVAL_IMAGE:-neurolab/gpt2giga-eval:v0.3.0}"
ENV_FILE="${NEUROLAB_ENV_FILE:-$PROJECT_ROOT/.env}"
MODEL="${OPENHANDS_EVAL_MODEL:-}"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
SYSTEM_CA_BUNDLE="${NEUROLAB_SSL_CERT_FILE:-/etc/ssl/certs/ca-certificates.crt}"

for required in "$FIXTURE_ROOT/calculator.py" "$FIXTURE_ROOT/test_calculator.py" "$OPENHANDS_BINARY" "$ENV_FILE" "$PYTHON_BIN" "$SYSTEM_CA_BUNDLE"; do
  if [[ ! -e "$required" ]]; then
    echo "Required local evaluation input is unavailable." >&2
    exit 1
  fi
done
if [[ ! -x "$OPENHANDS_BINARY" || ! -x "$PYTHON_BIN" ]]; then
  echo "OpenHands binary or project Python is not executable." >&2
  exit 1
fi

mkdir -p "$RUNTIME_ROOT"
umask 077
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVAL_ROOT="$(mktemp -d "$RUNTIME_ROOT/openhands-manual.${STAMP}.XXXXXX")"
case "$EVAL_ROOT" in
  "$RUNTIME_ROOT"/openhands-manual.*) ;;
  *) echo "Unsafe evaluation directory." >&2; exit 1 ;;
esac

WORKSPACE="$EVAL_ROOT/workspace"
PROXY_ENV="$EVAL_ROOT/gpt2giga.env"
AGENT_NETWORK="neurolab-oh-agent-${STAMP}-$$"
UPSTREAM_NETWORK="neurolab-oh-upstream-${STAMP}-$$"
PROXY_CONTAINER="neurolab-oh-proxy-${STAMP}-$$"

cleanup() {
  docker rm -f "$PROXY_CONTAINER" >/dev/null 2>&1 || true
  docker network rm "$AGENT_NETWORK" >/dev/null 2>&1 || true
  docker network rm "$UPSTREAM_NETWORK" >/dev/null 2>&1 || true
  if [[ -d "$EVAL_ROOT" ]]; then
    case "$EVAL_ROOT" in
      "$RUNTIME_ROOT"/openhands-manual.*) rm -rf -- "$EVAL_ROOT" ;;
      *) echo "Refusing to remove an unsafe evaluation directory." >&2 ;;
    esac
  fi
}
trap cleanup EXIT

show_sanitized_proxy_logs() {
  docker logs --tail 20 "$PROXY_CONTAINER" 2>&1 |
    sed -E 's/([A-Za-z_]*(key|token|credential|authorization)[A-Za-z_]*)[=:][^[:space:]]+/\1=[REDACTED]/Ig' >&2 || true
}

classify_agent_failure() {
  EVAL_EVENTS="$EVAL_ROOT/openhands-events.jsonl" "$PYTHON_BIN" -c '
import os
from pathlib import Path

payload = Path(os.environ["EVAL_EVENTS"]).read_bytes().lower()
categories = (
    (b"authentication", "authentication-or-proxy"),
    (b"unauthorized", "authentication-or-proxy"),
    (b"api key", "authentication-or-proxy"),
    (b"connection refused", "connectivity"),
    (b"name resolution", "connectivity"),
    (b"model", "model-or-provider"),
    (b"permission denied", "workspace-permission"),
    (b"read-only", "workspace-permission"),
    (b"timeout", "timeout"),
)
for marker, category in categories:
    if marker in payload:
        print(category)
        break
else:
    print("unclassified")
' 2>/dev/null || printf '%s\\n' 'unclassified'
}

write_redacted_agent_trace() {
  EVAL_EVENTS="$EVAL_ROOT/openhands-events.jsonl" REDACTED_TRACE="$RUNTIME_ROOT/openhands-manual-last-trace.redacted.log" "$PYTHON_BIN" -c '
import os
import re
from pathlib import Path

source = Path(os.environ["EVAL_EVENTS"])
target = Path(os.environ["REDACTED_TRACE"])
payload = source.read_text(encoding="utf-8", errors="replace") if source.exists() else ""
payload = re.sub(
    r"(?i)(authorization|api[_ -]?key|token|credential)(\s*[:=]\s*)([^\s,;]+)",
    r"\1\2[REDACTED]",
    payload,
)
payload = re.sub(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{24,}(?![A-Za-z0-9_-])", "[REDACTED_TOKEN]", payload)
target.write_text(payload, encoding="utf-8")
target.chmod(0o600)
' 2>/dev/null || true
}

# Parse the local env file as data. Only the GigaChat credential and its scope
# are copied into a 0600 disposable proxy env file; it is never sourced.
EVAL_PROXY_ENV="$PROXY_ENV" NEUROLAB_ENV_FILE="$ENV_FILE" "$PYTHON_BIN" -c '
import base64
import os
import secrets
from pathlib import Path

from dotenv import dotenv_values

source = dotenv_values(os.environ["NEUROLAB_ENV_FILE"])
credential_name = os.environ.get(
    "NEUROLAB_GIGACHAT_CREDENTIAL_ENV",
    source.get("GIGACHAT_PRIMARY_KEY_ENV", "GIGACHAT_CREDENTIALS"),
)
if not isinstance(credential_name, str) or not credential_name.isidentifier():
    raise SystemExit("Configured GigaChat credential variable name is invalid.")
credential = source.get(credential_name)
if not credential:
    raise SystemExit("Configured GigaChat credential is absent or empty.")
scope = source.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
model = source.get("GIGACHAT_MODEL", "GigaChat")
if not isinstance(model, str) or not model.strip() or "\r" in model or "\n" in model:
    raise SystemExit("Configured GigaChat model is invalid.")
api_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
Path(os.environ["EVAL_PROXY_ENV"]).write_text(
    "GIGACHAT_CREDENTIALS=" + credential + "\n"
    "GIGACHAT_SCOPE=" + scope + "\n"
    "GIGACHAT_MODEL=" + model.strip() + "\n"
    "OPENHANDS_EVAL_MODEL=" + model.strip() + "\n"
    "GPT2GIGA_API_KEY=" + api_key + "\n",
    encoding="utf-8",
)
'
chmod 600 "$PROXY_ENV"
PROXY_API_KEY="$(EVAL_PROXY_ENV="$PROXY_ENV" "$PYTHON_BIN" -c 'from dotenv import dotenv_values; import os; print(dotenv_values(os.environ["EVAL_PROXY_ENV"])["GPT2GIGA_API_KEY"])')"
if [[ -z "$MODEL" ]]; then
  MODEL="$(EVAL_PROXY_ENV="$PROXY_ENV" "$PYTHON_BIN" -c 'from dotenv import dotenv_values; import os; print(dotenv_values(os.environ["EVAL_PROXY_ENV"])["OPENHANDS_EVAL_MODEL"])')"
fi

mkdir -p "$WORKSPACE/openhands_eval_fixture"
cp "$FIXTURE_ROOT/calculator.py" "$WORKSPACE/openhands_eval_fixture/calculator.py"
cp "$FIXTURE_ROOT/test_calculator.py" "$WORKSPACE/openhands_eval_fixture/test_calculator.py"
git -C "$WORKSPACE" init --quiet
git -C "$WORKSPACE" config user.name "NeuroLab Synthetic Eval"
git -C "$WORKSPACE" config user.email "synthetic-eval@example.invalid"
git -C "$WORKSPACE" add openhands_eval_fixture
git -C "$WORKSPACE" commit --quiet -m "synthetic baseline"
if (cd "$WORKSPACE" && python3 -B -m unittest discover -s openhands_eval_fixture) >"$EVAL_ROOT/baseline.log" 2>&1; then
  echo "Synthetic baseline unexpectedly passed." >&2
  exit 1
fi
chmod -R a+rwX "$WORKSPACE"

docker network create --internal "$AGENT_NETWORK" >/dev/null
docker network create "$UPSTREAM_NETWORK" >/dev/null
docker run -d --rm --name "$PROXY_CONTAINER" --network "$UPSTREAM_NETWORK" \
  --env-file "$PROXY_ENV" \
  -e MODE=PROD \
  -e GPT2GIGA_HOST=0.0.0.0 \
  -e GPT2GIGA_PORT=8090 \
  -e GPT2GIGA_ENABLE_API_KEY_AUTH=true \
  -e SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 \
  -v "$SYSTEM_CA_BUNDLE:/etc/ssl/certs/ca-certificates.crt:ro" \
  "$EVAL_IMAGE" >/dev/null
docker network connect --alias gpt2giga "$AGENT_NETWORK" "$PROXY_CONTAINER"

if ! docker inspect --format '{{.State.Running}}' "$PROXY_CONTAINER" | grep -qx true; then
  echo "Disposable gpt2giga proxy did not start." >&2
  show_sanitized_proxy_logs
  exit 1
fi
PROXY_READY=0
for _ in $(seq 1 10); do
  if docker run --rm --network "$AGENT_NETWORK" --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=16m \
    --cap-drop ALL --security-opt no-new-privileges --pids-limit 32 \
    --entrypoint /usr/local/bin/python "$EVAL_IMAGE" \
    -c 'from urllib.request import urlopen; urlopen("http://gpt2giga:8090/health", timeout=2).read()' \
    >/dev/null 2>&1; then
    PROXY_READY=1
    break
  fi
  sleep 1
done
if [[ "$PROXY_READY" != "1" ]]; then
  echo "Disposable gpt2giga proxy did not become ready." >&2
  show_sanitized_proxy_logs
  exit 1
fi

# The agent has a writable synthetic workspace and a read-only CLI binary only.
# It sees the internal proxy but has neither a Docker socket nor a route outside
# that internal network. Its event stream is kept in the disposable directory.
set +e
docker run --rm --network "$AGENT_NETWORK" --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m --tmpfs /home/openhands:rw,nosuid,size=32m \
  --tmpfs /tmp/openhands-cache:rw,noexec,nosuid,size=32m \
  --tmpfs /tmp/openhands-runtime:rw,exec,nosuid,size=256m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 \
  -e OPENHANDS_SUPPRESS_BANNER=1 \
  -e HOME=/home/openhands \
  -e XDG_CACHE_HOME=/tmp/openhands-cache \
  -e TMPDIR=/tmp/openhands-runtime \
  -e LLM_API_KEY="$PROXY_API_KEY" \
  -e LLM_BASE_URL="http://gpt2giga:8090/v1" \
  -e LLM_MODEL="openai/$MODEL" \
  -v "$OPENHANDS_BINARY:/openhands:ro" \
  -v "$WORKSPACE:/workspace:rw" \
  -w /workspace \
  --entrypoint /openhands \
  "$EVAL_IMAGE" --headless --json --always-approve --exit-without-confirmation --override-with-envs \
  --task 'Edit only openhands_eval_fixture/calculator.py. The add function is intentionally wrong. Make the smallest correct fix, then run exactly: python3 -B -m unittest discover -s openhands_eval_fixture. Do not access network, Docker, environment files, or paths outside /workspace. Do not modify tests or any other file.' \
  >"$EVAL_ROOT/openhands-events.jsonl" 2>&1
AGENT_EXIT=$?
set -e
if [[ "$AGENT_EXIT" -ne 0 ]]; then
  FAILURE_KIND="$(classify_agent_failure)"
  write_redacted_agent_trace
  echo "OpenHands evaluation did not complete successfully ($FAILURE_KIND, exit $AGENT_EXIT); disposable state was removed." >&2
  exit "$AGENT_EXIT"
fi
write_redacted_agent_trace

if ! docker run --rm --network none --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=32m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 \
  -v "$WORKSPACE:/workspace:ro" -w /workspace \
  --entrypoint /usr/local/bin/python \
  "$EVAL_IMAGE" -B -m unittest discover -s openhands_eval_fixture; then
  echo "OpenHands result failed isolated verification." >&2
  exit 1
fi
git -C "$WORKSPACE" diff --check
CHANGED_PATHS="$(git -C "$WORKSPACE" diff --name-only)"
if [[ "$CHANGED_PATHS" != "openhands_eval_fixture/calculator.py" ]]; then
  echo "OpenHands changed an unapproved path; result rejected." >&2
  exit 1
fi

CHANGED_PATHS="$CHANGED_PATHS" "$PYTHON_BIN" -c '
import os
from neurolab.engineering_policy import require_reviewable_change

receipt = require_reviewable_change(
    changed_paths=os.environ["CHANGED_PATHS"].splitlines(),
    allowed_paths=("openhands_eval_fixture/calculator.py",),
    test_command="python3 -B -m unittest discover -s openhands_eval_fixture",
    test_exit_code=0,
)
if receipt.decision != "review_required":
    raise SystemExit("Unexpected acceptance decision.")
print("manual OpenHands synthetic evaluation validated: review_required")
'
