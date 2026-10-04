# ChatGPT project context

This directory is a local mirror of the ChatGPT project “НейроЛаб”.

- Treat every file under `sources/` as read-only reference material.
- Do not edit, rename, move, or delete synced project files.
- These files may be replaced the next time a task is created from this ChatGPT project.


## Project instructions

This project has no custom instructions.

## Обязательный порядок работы для агентов

Этот файл обязателен к прочтению **до любого действия в проекте**.

1. До начала работы прочитать [ROADMAP.md](ROADMAP.md) полностью и определить текущий этап, его критерии готовности, ограничения и следующий безопасный шаг.
2. Не начинать следующий этап, пока не зафиксирован результат предыдущего или не оформлено обоснованное исключение в журнале дорожной карты.
3. После завершения каждого этапа или существенного подэтапа немедленно обновить `ROADMAP.md`: указать дату, статус, фактический результат, выполненные тесты, проблемы и их решения, а также следующий шаг.
4. Обновлять дорожную карту по фактам. Нельзя отмечать работу завершённой без ссылок на проверяемые артефакты, команды/наборы тестов или явного объяснения, почему проверка пока невозможна.
5. Для изменений, затрагивающих клинические рекомендации, пациентские данные, безопасность, доступы или публикацию, соблюдать стоп-условия и процесс клинической валидации из `ROADMAP.md`. Такой функционал не считается готовым только по результатам технических тестов.

### Язык документации — русский

Все новые и изменяемые документы НейроЛаба писать на русском языке:
дорожную карту и её журнал, инструкции агентам, описания архитектуры,
отчёты, политики, карточки исследований, объяснения оценок и технические
задания, в том числе документы, создаваемые моделями. Не смешивать русский
текст с английскими описаниями действий и результатов, если есть понятная
русская формулировка. Перед передачей документа проверить его язык.

Без перевода сохранять названия продуктов и публикаций, пути, команды,
код, UUID, хеши, ключи схем и точные значения машинных статусов. При первом
упоминании непонятного статуса дать русское объяснение. Иноязычное название
или цитата источника не заменяет русского изложения результатов.

Это правило не разрешает менять синхронизированные исходные материалы,
неизменяемые результаты прошлых запусков, контрольные тесты или машинные
контракты. Старые англоязычные результаты отмечать как требующие русской
версии, не подменяя оригинальный результат. Проверка языка не заменяет
проверку содержания; до реализации автоматической проверки не выдавать
эту инструкцию за уже работающий программный запрет.

### Единственная дорожная карта

`ROADMAP.md` в корне репозитория — единственный канонический журнал и план
проекта. Любое обновление статуса, результата, проблемы, теста или следующего
шага записывается **только** туда.

Запрещено создавать, копировать или поддерживать альтернативные дорожные
карты: `ROADMAP.*.md`, `*_ROADMAP.md`, отдельные журналы этапов или
рассинхронизированные roadmap-файлы. Временные runtime-артефакты могут
содержать лишь машинный receipt конкретного запуска и не являются дорожной
картой. Перед созданием нового документа с планом агент обязан дописать или
сослаться на соответствующий раздел `ROADMAP.md`.

## Автономный исследовательский и инженерный цикл

В публичном synthetic-only контуре агент не требует ручного подтверждения
каждой статьи, карточки, claim или промежуточного ТЗ. Он самостоятельно
собирает и ранжирует evidence, накапливает corpus, определяет пробелы,
формирует следующую задачу поиска, пишет и тестирует код в изолированном
worktree, оценивает результат и выбирает `continue`, `repair`,
`harvest_parts`, `promote` или `retire` в пределах утверждённых budget/policy.

Самооценка автора не является доказательством. Любое promotion требует
детерминированных тестов и/или отдельного независимого evaluator; модель не
может единолично утвердить собственный источник, ТЗ, изменение кода или
изменение проверки качества.

Агенты могут предлагать и эволюционно улучшать article scorer, response-quality
evaluator и test-suite, но обязаны: сохранять неизменяемые safety-инварианты,
не удалять frozen regression/holdout cases, версионировать изменение, запускать
старую и новую проверку в shadow mode на сопоставимом наборе и иметь rollback.
Изменение evaluator допускается к promotion только при независимой проверке и
измеримом улучшении без safety-regression.

Каждый переход пишет redacted log: цель, версии агентов/графа/evaluator,
хеши входных артефактов, действие, тесты/метрики/стоимость, self-score,
independent score, решение и следующий автоматически сформированный шаг.
Не сохранять prompt, raw model output, PDF/text/image, секреты или данные
пациентов, если отдельная политика не разрешила их хранение.

Bounded validated experimental ТЗ разрешено хранить только по
`docs/governance/EXPERIMENTAL_SPEC_POLICY.md`. Оно не является reviewed
evidence или разрешением clinical/prod/merge; raw prompt/transcript исключён.

Более мощная внешняя модель может быть только независимым аудитором для
redacted evaluation packet: она диагностирует деградацию и предлагает план,
но не получает секреты/PHI, не меняет immutable policy и не может сама
promote evaluator, code или deployment. Реальные clinical/patient/production
действия по-прежнему требуют отдельных стоп-условий и авторизации.

### Формат обновления дорожной карты

### Восстановление RP5 и доказательства исполнения

После смены накопителя сначала проверить реальный runtime: disk/mounts,
Git diff, Compose, migration ledger, backup и count research artifacts.
Старые записи журнала не доказывают состояние новой БД. Не перезаписывать
`.env`, чужой Git diff или volumes; сохранять изменения до rollout.
Приватные SSH/Tailscale/proxy endpoints хранить только в ignored access-note.
Каждый новый live-pass требует receipt конкретного запуска, а не только
наличия старого card ID. Работать по разделу 7 ROADMAP без подтверждения
каждого synthetic подэтапа; clinical/prod границы остаются неизменными.

Перед paid model call проверять импорты CLI в offline regression suite.
Code agent не получает frozen tests или writable repo; первый эксперимент
запускается только через isolated runner с проверенным `memory.max`.
No continuous run до R7 durable resume/shared budget; timeout/error нельзя
превращать в success, а отсутствие token accounting — в нулевую стоимость.

Для fixed provenance family использовать готовый Ruff static gate плюс
неизменяемые frozen tests. Передавать модели failed case IDs и bounded
rule/line/column diagnostics; не чинить модельный candidate вручную и не
ослаблять тесты ради pass. Final outcomes записывать append-only в БД;
passing asset остаётся candidate, не auto-promoted/production.

Исходный `provenance-frozen-v1` (11 cases/50-DAG holdout) не менять.
Supplementary `provenance-cycles-v1` (9 cases/24 cyclic holdouts) запускается
отдельно и не монтируется агенту. Новый acceptance требует старые 11/11,
дополнительные 9/9, Ruff и runtime gate. Legacy 11/11 receipts остаются
неизменяемыми историческими результатами, не доказательством нового gate.
Повторная оценка пишет отдельный hash-linked receipt; failed reassessment
может инициировать модельный repair, но не ручную правку candidate.

R7 начать с official PostgresSaver и receipt-only durable reconciliation:
checkpoint содержит UUID/hash/metrics/decision, не prompts/cards/source/keys.
Serializer strict, pickle запрещён. Resume завершённых шагов не вызывает
модель повторно. Этот foundation не выдавать за полный paid search/code
orchestrator: shared budgets/outbox/provider attempt recovery ещё обязательны.

Если владелец отложил выбор нового бюджета, продолжать независимые R4/R6/R8
проверки с существующими лимитами, а не включать continuous paid graph.
Перед повторным live OpenHands запуском после no-op проверять pinned CLI
через offline tool replay и negative control. `exit 0` не доказывает запись
файла или прохождение evaluator. Не отключать security analyzer и не
подставлять `security_risk` вместо модели в реальном gateway: обязательные
аргументы должна выдать сама модель. Диагностика содержит только fixed
error categories/counters; prompts, tool arguments и raw errors не хранить.
Vision принимает только complete `finish_reason=stop`; отдельный redacted
receipt сохраняет попытки, known usage и cleanup. Missing usage — unknown,
не нулевая стоимость; extracted card остаётся needs_review до independent gate.

R8 использует existing scholarly adapters, не новый агент. `corpus-gap-v1`
сохраняется как legacy; текущие маршруты применяют `research-selection-v1`.
Одна invocation допускает максимум один reserved search (по 2 metadata records
на provider), ни одного LLM call. Шаблон резервируется в PostgreSQL до сети;
inflight/unavailable/completed не повторяются автоматически. После исчерпания
шести шаблонов остановить discovery, разбирать очередь lawful fulltext либо
версионировать новую search policy по измеренным пробелам, не стирать history.
Не выводить truth/reproduction из title или provider count. Теория остаётся
в balanced exploration lane; уже сохранённый PDF не скачивать снова только
из-за needs_review card. Metadata coverage pass не является разрешением
полного ТЗ: independent semantic/spec gate требуется отдельно.
PDF preflight также резервирует один corpus source до license request;
без compatible explicit licence PDF не скачивается. Неясный license/network
отказ не выдавать за доказательство copyright ban. Failed/inflight preflight
не повторяется автоматически, source остаётся metadata; successful document
receipt ещё не означает verified claims или разрешение на полный ТЗ.

Document-analysis-v2 разрешает bounded validated intermediate WindowNote/card
cache в ignored runtime (0600, до 48 KiB на step) только для возобновления
того же exact PDF/model/prompt-version. Cache не содержит PDF, извлечённый
текст, prompt или raw reply. Hash и strict schema повторно проверяются перед
reuse. Step резервируется exact-key lock до generation; stale lock/inflight,
timeout/unknown и invalid output блокируют автоматический повтор. Definite
429 допускает максимум вторую попытку; completed step не вызывает модель.
Каждый run сохраняет redacted attempts/known usage даже при отказе; SDK retry
disabled, finish_reason=stop обязателен. Cache не является account-wide budget
или полноценным R7 orchestration. Новая card остаётся needs_review; структурный
assessment не является semantic verification или reproduction.

### Трёхступенчатый отбор IT-исследований

`research-selection-v1`: trusted mission/problem → title+abstract admission →
exact-PDF/card content utility → task-specific experimental packet. Все три
ступени обязательны в automatic search/PDF/text/Vision/spec routes. Title-only
или missing abstract означает hold, не reject и не permission paid analysis.
Нерелевантность задаче не означает научную недостоверность; theory остаётся
exploration, без автоматического build/prod. Старые source/card rows не удалять.
Нельзя подавать в ТЗ карточку только за schema/coverage pass или высокий self-score.
Receipts append-only, hash-linked к mission/metadata/card/PDF; source text,
abstract, prompts и raw replies не хранятся. Content utility использует только
cited pages и остаётся lexical baseline, НЕ independent semantic entailment.
Input identity включает mission hash: изменение trusted goal не переиспользует
прежний verdict. Packet включает только findings на admitted ranges; diagram
page также должна входить в них, полезность всего PDF не наследуется автоматически.
Исходный metadata_title_v1 и frozen 13-case selection cohort сохранять; следующий
judge/evaluator сравнивать с ними в shadow. Старые failed/inflight PDF attempts
не повторять автоматически при смене selection policy. JEV и новые paid budgets
не включать без отдельного решения; full-spec/clinical gates остаются закрыты.

### Разбор PDF под задачу

Режим `task-document-v1` включается только для одной допущенной доверенной
задачи. Карточки сохранять отдельно в `task_document_cards`, без обновления
общего пересказа или прежних оценок. Каждый вывод разделяет сведения статьи,
предложенное применение и пробелы; объяснения пишутся на русском. Оценки
независимой воспроизводимости и независимости источника оставлять `null`.
Числовые опоры проверять в части «В статье», не в предложении модели.

Прежний отбор запускать только для сравнения; новый режим не меняет допуск
к ТЗ и не повышает статус до проверенного содержания. Подготовленный контракт
смысловой оценки не называть подключённым независимым оценщиком. Другое имя
модели не доказывает реальную независимость или доступ к ней; до утверждённого
профиля, бюджета и сравнительных проверок внешние вызовы не выполнять.
Не усекать длинные свидетельства; не сохранять исходный текст пакета проверки.

### Формат записи

Добавить или заполнить запись в разделе «Журнал выполнения» `ROADMAP.md`:

```markdown
| Дата (YYYY-MM-DD) | Этап / подэтап | Статус | Фактический результат | Тесты / доказательства | Проблемы и решения | Следующий шаг |
|---|---|---|---|---|---|---|
| 2026-09-13 | 1.1 | выполнен | ... | ... | ... | ... |
```

Статусы: `не начат`, `в работе`, `заблокирован`, `выполнен`, `отложен`.
