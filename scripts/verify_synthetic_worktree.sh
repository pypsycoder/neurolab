#!/usr/bin/env bash
# Exercise a synthetic-only worktree: failing test, fixed fixture, passing test, diff.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TEMPLATE_ROOT="$PROJECT_ROOT/tests/fixtures/synthetic-worktree"
RUNTIME_ROOT="$PROJECT_ROOT/runtime"

if [[ ! -f "$TEMPLATE_ROOT/calculator.py" || ! -f "$TEMPLATE_ROOT/fixed_calculator.py" || ! -f "$TEMPLATE_ROOT/test_calculator.py" ]]; then
  echo "Synthetic worktree fixture is incomplete" >&2
  exit 1
fi

mkdir -p "$RUNTIME_ROOT"
WORKTREE_DIR="$(mktemp -d "$RUNTIME_ROOT/synthetic-worktree.XXXXXX")"
case "$WORKTREE_DIR" in
  "$RUNTIME_ROOT"/synthetic-worktree.*) ;;
  *) echo "Unsafe temporary worktree path" >&2; exit 1 ;;
esac
cleanup() {
  if [[ -d "$WORKTREE_DIR" ]]; then
    rm -rf -- "$WORKTREE_DIR"
  fi
}
trap cleanup EXIT

cp "$TEMPLATE_ROOT/calculator.py" "$WORKTREE_DIR/calculator.py"
cp "$TEMPLATE_ROOT/test_calculator.py" "$WORKTREE_DIR/test_calculator.py"

export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL=/dev/null
git -C "$WORKTREE_DIR" init --quiet
git -C "$WORKTREE_DIR" config user.name "NeuroLab Synthetic Test"
git -C "$WORKTREE_DIR" config user.email "synthetic-worktree@example.invalid"
git -C "$WORKTREE_DIR" add calculator.py test_calculator.py
git -C "$WORKTREE_DIR" commit --quiet -m "synthetic baseline"

if (cd "$WORKTREE_DIR" && python3 -B -m unittest -q) >"$WORKTREE_DIR/baseline-test.log" 2>&1; then
  echo "Synthetic baseline unexpectedly passed" >&2
  exit 1
fi
echo "synthetic baseline failure observed"

cp "$TEMPLATE_ROOT/fixed_calculator.py" "$WORKTREE_DIR/calculator.py"
(cd "$WORKTREE_DIR" && python3 -B -m unittest -q)
git -C "$WORKTREE_DIR" diff --check

if [[ "$(git -C "$WORKTREE_DIR" diff --name-only)" != "calculator.py" ]]; then
  echo "Synthetic worktree changed an unapproved path" >&2
  exit 1
fi

echo "synthetic worktree validated: failing baseline → passing fix → calculator.py diff"
