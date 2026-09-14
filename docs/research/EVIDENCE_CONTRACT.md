# Контракт public-source evidence

`neurolab.research_evidence` — только локальная synthetic schema для будущего
research pipeline. Он не выполняет поиск, не открывает URL, не запускает LLM и
не использует медицинские или пациентские данные.

Для каждого источника требуются public `https` URL без credentials, название,
даты публикации и проверки, уровень evidence и явно записанные ограничения.
Отчёт требует не менее двух разных доменов и возвращает лишь
`review_required`.

`raw_excerpt` считается недоверенными данными. Он не включается в audit или
итоговое решение: вместо него сохраняется digest для сопоставления будущего
trace. Модель не извлекает факты и не делает clinical conclusion.

Подключение настоящего search/provider возможно только отдельным подэтапом:
нужны разрешение, schema вызова, transport sandbox, redacted trace, лимиты и
negative tests для ошибок/инъекций.
