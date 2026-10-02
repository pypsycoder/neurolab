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
