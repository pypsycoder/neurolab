#!/usr/bin/env bash
# Validate the execution boundary for future public-artifact reproduction runs.
# This runner deliberately accepts no repository URL, archive, branch or code
# supplied by a paper. It executes only the versioned synthetic fixture.
set -euo pipefail

if [[ "${RUN_DISPOSABLE_REPRODUCTION_EVAL:-0}" != "1" ]]; then
  echo "Set RUN_DISPOSABLE_REPRODUCTION_EVAL=1 for the synthetic-only sandbox check." >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
FIXTURE_ROOT="$PROJECT_ROOT/tests/fixtures/synthetic-worktree"
RUNTIME_ROOT="$PROJECT_ROOT/runtime"
EVAL_IMAGE="${REPRODUCTION_EVAL_IMAGE:-neurolab/gpt2giga-eval:v0.3.0}"

for required in "$FIXTURE_ROOT/calculator.py" "$FIXTURE_ROOT/fixed_calculator.py" "$FIXTURE_ROOT/test_calculator.py"; do
  if [[ ! -f "$required" ]]; then
    echo "Synthetic reproduction fixture is incomplete." >&2
    exit 1
  fi
done

mkdir -p "$RUNTIME_ROOT"
SANDBOX_ROOT="$(mktemp -d "$RUNTIME_ROOT/disposable-reproduction.XXXXXX")"
case "$SANDBOX_ROOT" in
  "$RUNTIME_ROOT"/disposable-reproduction.*) ;;
  *) echo "Unsafe disposable sandbox path." >&2; exit 1 ;;
esac
cleanup() {
  if [[ -d "$SANDBOX_ROOT" ]]; then
    case "$SANDBOX_ROOT" in
      "$RUNTIME_ROOT"/disposable-reproduction.*) rm -rf -- "$SANDBOX_ROOT" ;;
      *) echo "Refusing to remove an unsafe sandbox path." >&2 ;;
    esac
  fi
}
trap cleanup EXIT

WORKSPACE="$SANDBOX_ROOT/workspace"
mkdir -p "$WORKSPACE"
cp "$FIXTURE_ROOT/fixed_calculator.py" "$WORKSPACE/calculator.py"
cp "$FIXTURE_ROOT/test_calculator.py" "$WORKSPACE/test_calculator.py"
chmod -R a=rX,u+w "$WORKSPACE"

# The digest is a receipt for this known fixture, not a statement about any
# upstream repository. It helps assert that the execution input is immutable.
INPUT_SHA256="$(cd "$WORKSPACE" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | awk '{print $1}')"

timeout 30s docker run --rm --network none --read-only --user 65534:65534 \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 \
  -v "$WORKSPACE:/workspace:ro" -w /workspace \
  --entrypoint python3 "$EVAL_IMAGE" -B -m unittest -q

echo "disposable reproduction sandbox validated: fixture-only; network=none; tests=passed; input_sha256=$INPUT_SHA256"
