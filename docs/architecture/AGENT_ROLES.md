# Роли агентного графа

`neurolab.agent_roles` задаёт local-only policy default-deny. Она не запускает
инструменты и не предоставляет доступы: перед реальным вызовом будущий граф
должен отдельно пройти transport-, schema- и sandbox-проверки.

| Роль | Единственные разрешённые действия |
|---|---|
| Supervisor | `workflow.plan`, `workflow.route`, `workflow.cancel`, `workflow.report` |
| Researcher | `research.evidence.inspect` |
| Developer | `engineering.worktree.edit` |
| Tester | `engineering.worktree.test`, `policy.validate` |
| Reviewer | `engineering.diff.review` |
| Synthesizer | `report.compose` |

Любое неизвестное действие или роль отклоняется. В частности, в policy нет
shell, Docker socket, Git push/merge, deploy, чтения `.env`, секретов, внешней
сети, RAG или clinical-инструментов.

`required_role_actions()` описывает минимальную synthetic инженерную цепочку,
которую проверяет architecture smoke. Это доказательство разделения
полномочий, а не подключение реальных агентов или сервисов.

`neurolab.agent_transitions` добавляет отдельный default-deny gate для
передачи управления. Разрешён только линейный путь
`planned → routed → worktree_edited → tested → reviewed → reported` с точно
заданными ролью и действием на каждом шаге. Пропуск, повтор, обратный переход
или замена роли отклоняются до исполнения.

`neurolab.agent_receipts` хранит только состояния, названия ролей и действий
этой synthetic цепочки. После каждого hand-off создаётся новый receipt с
детерминированным SHA-256 digest; проверка отклоняет изменение состояния,
перехода или их порядка. Это локальная проверка целостности в памяти, а не
подписанный audit trail, не база данных и не хранилище clinical data.

Архитектурный receipt нельзя финализировать из промежуточного состояния:
`require_completed_transition_receipt()` принимает только проверенную цепочку,
дошедшую до `reported`. Поэтому при остановке или пропуске этапа итоговое
решение не создаётся (fail-closed).
