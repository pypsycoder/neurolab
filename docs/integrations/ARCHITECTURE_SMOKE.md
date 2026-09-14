# Детерминированный architecture smoke

`scripts/verify_architecture_smoke.sh` — локальный RP5-runner для одной
полностью synthetic архитектурной цепочки. Он не читает `.env`, не запускает
LLM, OpenHands, Hermes, внешний поиск или рабочий репозиторий.

## Что входит

1. Базовый synthetic smoke: policy, stdio MCP, LangGraph, Docker fixture/Git
   diff и controlled worktree с падением теста до правки и успехом после неё.
2. `neurolab.agent_roles`: default-deny allowlist ролей и действий; цепочка
   smoke проверяет разделение полномочий до создания итогового receipt.
3. `neurolab.agent_transitions`: default-deny state machine разрешает только
   пять заранее описанных forward-only hand-off между ролями.
4. `neurolab.agent_receipts`: in-memory receipt подтверждает порядок
   hand-off и детектирует изменение цепочки по digest; незавершённая цепочка
   fail-closed и не может породить итоговое решение.
5. `neurolab.agent_budget`: ограничивает synthetic scenario пятью hand-off,
   5 секундами локальной policy-оценки и нулём внешних вызовов/cost units.
6. `neurolab.architecture_smoke`: минимальный orchestration receipt, который
   требует одновременно validated engineering workflow, role policy,
   transition policy, verified receipt, untrusted MCP trace и allowlisted
   tested diff.
3. `require_reviewable_change`: единственный успешный исход —
   `review_required`. Runner не делает merge, push или deploy.

## Границы

- MCP-results остаются недоверенными данными; их content не включается в
  итоговый report.
- Worktree создаётся и удаляется внутри ignored `runtime/`.
- Контейнерные проверки не получают сеть, Docker socket, `.env` или основной
  checkout.
- Manual OpenHands runbook не вызывается этим скриптом: это отдельный
  approval-gated сценарий.

## Проверяемый результат

Успешный запуск печатает:

```text
review_required: workflow:validated
  → roles:default-deny
  → transitions:forward-only
  → receipt:verified-chain
  → receipt:complete
  → budget:within-limits
  → mcp-policy:accepted-untrusted-data
  → worktree-evidence:constrained
  → acceptance:review_required
```

Это техническое архитектурное доказательство, а не разрешение на
исследовательский поиск, RAG, клинический контур или работу с пациентскими
данными.
