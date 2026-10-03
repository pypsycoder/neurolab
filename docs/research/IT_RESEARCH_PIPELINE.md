# IT research → накопительный корпус → ТЗ для Code agent

Правила многомерной оценки теории, практических результатов, зрелости и
замкнутого цикла заданы в
[EVIDENCE_SCORING_AND_LIFECYCLE.md](EVIDENCE_SCORING_AND_LIFECYCLE.md).

`scripts/run_it_research.py` выполняет bounded public IT-research на RP5:

```bash
PYTHONPATH=src runtime/langgraph-eval/bin/python scripts/run_it_research.py \
  --topic "agentic code review architecture" \
  --goal "Design a review-only Code-agent change for evidence-gated tooling"
```

Он обращается только к фиксированным API `export.arxiv.org`,
`api.openalex.org` и `api.crossref.org`, не открывает URL из выдачи, не
запускает Hermes/LLM и не исполняет content источников. URL, abstract и PDF —
недоверенные данные. При недоступности одного провайдера контур продолжает
работу только при наличии как минимум двух независимых public domains; иначе
не создаёт ТЗ.

arXiv запрашивается как свежая bounded-лента категорий `cs.AI`, `cs.SE`,
`cs.CL` и `cs.IR`; затем возвращаются только наиболее совпадающие с темой
заголовки. Это избегает хрупкого длинного phrase-query и не загружает PDF.

Первый проход — только discovery: он не вправе выдать ТЗ для Code agent.
`latest-code-agent-task.md` в этот момент является отказом с перечнем
недостающего покрытия, а не заданием. Метаданные накапливаются в отдельной
PostgreSQL-схеме `it_research`; в ней нет пациентов, clinical data, секретов,
raw prompt, PDF или raw abstract. Сохраняются только public metadata,
provenance, хеш abstract и прозрачные оценки.

Для записи в корпус запускается изолированный одноразовый контейнер на RP5:

```bash
docker compose --profile research run --rm research \
  --topic "agentic code review architecture" \
  --goal "Design an evidence-gated IT research workflow" \
  --persist
```

До синтеза обязательны все условия versioned coverage gate:

- минимум 12 дедуплицированных источников и минимум две независимые
  provenance-площадки;
- минимум по три источника на каждый уровень: глобальная архитектура,
  подсистема, компонент, фича;
- минимум четыре источника с отдельно подтверждёнными content/code/data/reproduction
  сигналами;
- средняя воспроизводимость по компонентам и фичам не ниже 0,35.

Оценки раздельны: conceptual support, implementation readiness,
reproducibility и source independence. Поэтому теоретическая работа может
иметь высокую концептуальную ценность, но не может ложно поднять готовность
к реализации; vendor case с кодом не становится независимой репликацией.
Синтез возможен только после `ready_for_synthesis` и всё равно остаётся
`review_required`: он требует worktree, tests, diff и ручной review и запрещает
merge, push, deploy, доступ к `.env` и любую clinical/patient работу.

`OPENALEX_API_KEY` и `CROSSREF_MAILTO` опциональны. Их передают только
из `.env` в одноразовый container process; значения не попадают в URL,
артефакты или Git. Миграция `postgres/migrations/20260915_01_it_research_corpus.sql`
применяется явно к уже работающей БД: `init.sql` для этого не изменяется.

## Второй контур: ограниченная publisher/code evidence

Metadata discovery не должен становиться единственным источником истины, но
переход от него к контенту идёт только через узкие provider-specific adapters.
Первый такой маршрут для статей издателя — F1000Research:

```bash
PYTHONPATH=src runtime/langgraph-eval/bin/python scripts/run_f1000_html_evidence.py \
  --source-key "<existing corpus source key>" --article-id 14-905 --version 1 --persist
```

Он формирует URL сам и не принимает URL, redirect, cookie, login или PDF. Он
требует явный CC-BY 4.0, ограничивает ответ 2 MiB, отбрасывает script/style и
передаёт не более 2 000 символов **только человеку на review**. PostgreSQL
получает receipt: хеш HTML, хеш видимого текста, длину, лицензию и дату — без
HTML, excerpt, prompt или автоматически созданного claim. Даже успешный
receipt не делает источник `content_verified` и не открывает Code-agent ТЗ.
HTML-хеш может меняться из-за служебной разметки страницы; дедупликация receipt
основана на нормализованном видимом тексте, а технический HTML-хеш обновляется
до последнего наблюдения.

Для публичной реализации существует отдельный GitHub metadata route:

```bash
PYTHONPATH=src runtime/langgraph-eval/bin/python scripts/verify_public_repository.py \
  --source-key "<existing corpus source key>" --claim-id "<human-reviewed UUID>" \
  --repository owner/repository --persist
```

Он получает только fixed `api.github.com` metadata/tree: SPDX-лицензию и
сигналы README/tests/environment/data. Не загружает, не сохраняет и не
исполняет код, README или данные. Запись в corpus возможна лишь после
human-reviewed claim, связанного с тем же source. Это поднимает качество
reproducibility evidence, но не заменяет pinned-snapshot, независимый sandbox
reproduction и отдельное ручное решение.

Если конкретная работа уже отобрана вручную, её можно добавить в corpus через
точный OpenAlex DOI lookup — без свободного поиска и без перехода по publisher
URL:

```bash
PYTHONPATH=src runtime/langgraph-eval/bin/python scripts/import_openalex_doi_record.py \
  --doi 10.12688/f1000research.169927.1 \
  --topic "agentic system architecture evidence-gated research orchestration" \
  --goal "Collect review-only public architecture evidence" --persist
```

Операционный запуск с `--persist` выполняется в существующем изолированном
research container, которому передаётся `DATABASE_URL` только процессом
Compose. CLI встроен в immutable research image; при изменении нужно
пересобрать образ и не использовать writeable source mount. Точечный importer принимает исключительно DOI и сверяет, что
возвращённый OpenAlex DOI совпадает с запрошенным; запись остаётся
`metadata_observed` до независимого ручного claim review.

## Трёхступенчатый отбор `research-selection-v1`

Текущий автономный маршрут отделяет три вопроса: что искать, относится ли
аннотация к задаче, какие конкретные страницы полезны для эксперимента.
Шесть доверенных миссий задают узкие параметры поиска: architecture, workflow,
evaluation, provenance, contracts и theory. Заголовок без аннотации не даёт
допуск; неопределённость сохраняется как `hold`, теория — как `explore`.
Нерелевантные записи не удаляются из corpus.

```bash
# Повторная оценка существующего публичного источника, без вызовов модели:
python scripts/run_research_selection.py --source-key '<64-hex source key>' \
  --refresh-metadata --assess-content
```

По умолчанию ограничение — два источника, максимум шесть по явному `--limit`.
Для arXiv проверяется точная версия: аннотация обрабатывается временно, в БД
сохраняются только её хеш и redacted verdict. Content-only запуск без
`--refresh-metadata` использует существующий hash-validated допуск, не
подменяет аннотацию пустой строкой. PDF обрабатывается в памяти с проверкой
точного хеша и прежними лицензионными/сетевыми ограничениями.

Без metadata-допуска закрыты PDF-очередь и новые text/Vision-вызовы GigaChat.
ТЗ для `synthetic_provenance_graph` получает только карточки, допущенные
именно по provenance, и findings на разрешённых страницах. Схема не наследует
полезность всего PDF: её страница также должна входить в разрешённый диапазон.
Старые failed/inflight PDF-попытки автоматически не повторяются.

Это **лексический baseline**, не семантическая проверка, научная достоверность
или воспроизведение результатов. Совпадение слов на указанной странице не
доказывает истинность тезиса. JEV/другая judge-модель и новые бюджеты не
включены; полный production/clinical ТЗ по этим verdict запрещён. Frozen
сравнение 13 synthetic кейсов оценивает только task relevance. История,
фактические проверки и следующий шаг ведутся исключительно в `ROADMAP.md`.
