# neuro-lab control plane

Воспроизводимый always-on control plane для Raspberry Pi 5. Compose project изолирован от существующего `sing-box` и не публикует PostgreSQL или Redis на хост.

## Сервисы

- PostgreSQL 17 хранит задачи, события и фактическое usage.
- Redis держит очередь `neuro-lab:tasks`.
- Два worker'а выполняют GigaChat chat и embeddings запросы.
- Primary и Freemium credentials выбираются явно через `credential_lane`; автоматический переход на платный OpenRouter отсутствует.
- Отдельный monitor сохраняет температуру и базовые метрики Pi раз в минуту; история ограничена 30 днями.

## Payload для чата

```json
{
  "provider": "gigachat",
  "operation": "chat",
  "credential_lane": "primary",
  "model": "GigaChat-3-Pro",
  "messages": [{"role": "user", "content": "Задача"}],
  "temperature": 0.2,
  "max_tokens": 512
}
```

## Payload для эмбеддингов

```json
{
  "provider": "gigachat",
  "operation": "embeddings",
  "credential_lane": "primary",
  "model": "GigaEmbeddings-3B-2025-09",
  "input": ["первый текст", "второй текст"]
}
```

## Проверка моделей

Из контейнера проекта можно поставить в очередь минимальный probe всех моделей первого ключа и получить компактный отчёт без вывода credentials и embedding vectors:

```bash
cd /opt/neuro-lab
docker compose run --rm orchestrator python probe_models.py --lane primary
```

Ограничить проверку одной моделью:

```bash
docker compose run --rm orchestrator python probe_models.py \
  --lane primary --model GigaChat-3-Ultra
```

## Запуск

```bash
cd /opt/neuro-lab
docker compose config --quiet
docker compose up -d
./scripts/apply_migrations.sh --apply
docker compose ps
```

При обновлении кода с новой миграцией сначала поднять PostgreSQL, затем
выполнить `./scripts/apply_migrations.sh --apply`, и только после этого
пересоздавать worker/monitor. Скрипт не исполняет `.env` и ведёт в БД
идемпотентный журнал применённых имён миграций.

## Проверка durable delivery

После изменения worker или Redis/PostgreSQL delivery-кода на RP5 можно
запустить opt-in E2E-проверку:

```bash
./scripts/verify_control_plane_delivery_e2e.sh --apply
```

Она не читает `.env`, не вызывает GigaChat и создаёт только три новых
synthetic `local-smoke-test` задания. Проверяются exactly-one cost event при
duplicate delivery, возврат просроченной execution lease и recovery сообщения,
которое попало в processing queue до PostgreSQL claim. Перед recovery скрипт
останавливается, если уже обнаружил чужие просроченные `running` задания: такие
задания требуют отдельного разбора, а не теста.

## Web-панель

После запуска dashboard доступен только локально на Pi по `http://127.0.0.1:8080`. Для безопасного удалённого доступа через tailnet включить Tailscale Serve и создать HTTPS proxy:

```bash
tailscale serve --bg 8080
tailscale serve status
```

Не использовать `tailscale funnel` для админ-панели: Funnel делает сервис доступным публично.

После настройки панель доступна только пользователям tailnet по `<private Tailnet HTTPS URL>`. Отключить proxy можно командой:

```bash
sudo tailscale serve --https=443 off
```

В верхней части панели — график температуры Raspberry Pi. Переключатели `1 час`, `12 часов` и `сутки` меняют историческое окно. Остальные системные показатели сделаны компактными, а данные обновляются автоматически.

## Веб-поиск

GigaChat chat API сам по себе не получает доступ к интернету от этого control plane. Для задач с внешними источниками будет добавлен отдельный тип задания `web-research`: внешний поисковый провайдер вернёт URL и выдержки, а GigaChat получит их как контекст для итогового ответа. Такой маршрут должен включаться отдельно, с лимитами стоимости; OpenRouter остаётся выключенным, пока пользователь явно не разрешит его использование.
