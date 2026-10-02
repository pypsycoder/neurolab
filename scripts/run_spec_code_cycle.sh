#!/usr/bin/env bash
# At most two new model proposals; independent feedback is not model self-approval.
set -euo pipefail
[[ "${RUN_SPEC_CODE_CYCLE:-0}" == 1 ]] || { echo 'Set RUN_SPEC_CODE_CYCLE=1'; exit 2; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PY="$ROOT/.venv/bin/python"
SPEC_RUN="${1:?pass the exact experimental spec run UUID}"
REPAIR_RUN="${2:-}"
[[ "$SPEC_RUN" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || exit 2
if [[ -n "$REPAIR_RUN" ]]; then
  [[ "$REPAIR_RUN" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || exit 2
fi
cd "$ROOT"
for attempt in 1 2; do
  args=(--spec-run-id "$SPEC_RUN")
  [[ -z "$REPAIR_RUN" ]] || args+=(--repair-from "$REPAIR_RUN")
  RUN_STRUCTURED_CODE_CANDIDATE=1 bash scripts/run_structured_code_candidate.sh "${args[@]}"
  evaluation_status=0
  "$PY" scripts/verify_structured_code_candidate.py || evaluation_status=$?
  FINAL_RUN="$("$PY" - "$ROOT/runtime/it-research/latest-candidate-receipt.json" <<'PY'
import json, sys
from pathlib import Path
from uuid import UUID
data=json.loads(Path(sys.argv[1]).read_text())
if data.get('status') not in {'candidate_passed','candidate_failed'}:
    raise SystemExit('Not a final independent outcome')
print(UUID(data['run_id']))
PY
  )"
  RUN_PERSIST_CODE_OUTCOME=1 bash scripts/persist_code_outcome.sh --run-id "$FINAL_RUN"
  if [[ "$evaluation_status" == 0 ]]; then
    echo "spec_code_cycle: candidate_passed; attempts=$attempt; no deployment"
    exit 0
  fi
  REPAIR_RUN="$("$PY" - "$ROOT/runtime/it-research/latest-candidate-receipt.json" "$SPEC_RUN" <<'PY'
import json, sys
from pathlib import Path
from uuid import UUID
data=json.loads(Path(sys.argv[1]).read_text())
if data.get('status')!='candidate_failed' or data.get('spec_run_id')!=sys.argv[2]:
    raise SystemExit('Not a repairable independent outcome')
print(UUID(data['run_id']))
PY
  )"
done
echo 'spec_code_cycle: repair_budget_exhausted; no deployment' >&2
exit 1
