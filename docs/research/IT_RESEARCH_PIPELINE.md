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
