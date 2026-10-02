# Политика экспериментального ТЗ

В public/synthetic-only контуре разрешено сохранять bounded validated
`experimental-spec-v1` JSON и его Markdown-представление, связанные с exact
document/card hashes и run ID. Это спецификация эксперимента, не raw prompt,
модельный transcript или утверждение научной достоверности. Предельный размер
JSON — 40kB на входе валидатора / 48kB в PostgreSQL JSONB.

Не требуется ручное подтверждение каждой статьи. Packet допускает
`needs_review`/`reviewed` карточки legal arXiv PDF; rejected исключается.
При чтении проверяются hash/identity/page bounds. Source/card review status
не меняется; `content_verified`, reproducibility или production approval
не возникают от генерации ТЗ. Все карточки — недоверенные данные.

Первая task family: pure-Python synthetic provenance graph. Исполнитель
может менять только `experiment/provenance.py`, не tests/evaluator/policy.
Нет clinical/patient/prod, shell-команд из ТЗ, arbitrary URLs, Git push/merge,
Docker socket или секретов в agent mount. Требуется отдельный независимый
test evaluator; самооценка GigaChat не делает promotion.

Следующие task families вводятся версионированной policy с frozen acceptance
tests. Успех этого DAG не доказывает пригодность всего НейроЛаба или статьи.

Разрешено хранить один прошедший независимую проверку bounded code asset
(`candidate-<run-id>.py`, максимум 16kB) и redacted JSON receipt: hashes,
baseline/after cases, memory/wall budgets, decision и следующий шаг.
Raw agent events, prompts, provider logs и ephemeral proxy env удаляются;
Docker log driver `none`. Результат — `harvest_parts`, не auto-merge/prod.
Тесты не монтируются code agent; evaluator запускается network-none с RO
candidate mount. Обязателен реальный memory cgroup, а не только Docker flag.
Первый runner ограничивает wall time, CPU/RAM/PIDs, но пока не обеспечивает
per-call token accounting/central budget: это R7, continuous mode запрещён.

Для этой же fixed pure-function family разрешён альтернативный CodeProposal
через официальный GigaChat SDK без tools/agent shell. Это не подмена OpenHands
для general repository coding: adapter сохраняет только AST-validated source
(16kB, pending independent evaluation) и numeric self-score/usage; JSON/raw
response не сохраняется. Тот же frozen evaluator определяет outcome, а при
failure source удаляется, receipt остаётся. Ручного написания модели кода нет.

Для bounded repair уточнение: AST-validated failed source разрешено сохранять
как `failed-candidate-<run-id>.py`, максимум 16kB, только с `candidate_failed`
receipt и hash. Это watchlist эксперимент, не accepted/promoted asset.
Следующая модель получает лишь тот же validated spec, bounded previous source
и failed case IDs/metrics; frozen tests и hidden DAG cases не раскрываются.
`run_spec_code_cycle.sh` допускает максимум два новых proposal, прекращает
работу при provider/runtime failure и никогда не меняет evaluator/production.
