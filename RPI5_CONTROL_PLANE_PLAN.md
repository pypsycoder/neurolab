# Raspberry Pi 5 — control plane R&D-лаборатории

Обновлено: 2026-09-13 (Europe/Moscow)

## Цель

Подготовить Raspberry Pi 5 как постоянно работающий control plane для R&D-лаборатории нейроассистента. Он координирует задания, хранит метаданные и стоимость вызовов, но не является постоянным местом для тяжёлых данных до установки NVMe.

## Принципы безопасности

- Существующие OpenClaw, контейнеры, образы, тома и данные не удаляются, не перезапускаются и не изменяются без отдельной проверки.
- Новый стек изолирован Docker Compose project name `neuro-lab` и каталогом `/opt/neuro-lab`; его имена томов не пересекаются с чужими проектами.
- До NVMe сохраняются только конфигурации и умеренные логи. PostgreSQL, Redis, Docker image cache и артефакты планово переносятся на NVMe.
- Пароли и API-ключи находятся только в `/opt/neuro-lab/.env`, который не добавляется в Git. В репозиторий входит лишь `.env.example`.
- Любое обновление ОС, установка пакетов, запуск контейнеров или изменение systemd выполняется только после фактической инвентаризации и подтверждения доступного дискового пространства.

## Текущее состояние: подтверждено

| Компонент | Состояние |
| --- | --- |
| Устройство | Raspberry Pi 5 rev 1.0, 8 GB |
| ОС | Debian GNU/Linux 13.7 (Trixie), Raspberry Pi kernel `6.18.39+rpt-rpi-2712` |
| Архитектура | aarch64 / arm64 |
| Raspberry Pi Connect | 2.12.2, устройство online |
| Удалённый доступ | Tailscale: `<private Tailscale IPv4>`, `<private Tailnet hostname>`; TCP/22 отвечает |
| Connect capabilities | Screen sharing и Remote shell разрешены |
| NVMe | ожидается, не считается доступным в этой фазе |
| Системный диск | microSD `mmcblk0`, 116.5 GB; root ext4: 96 GB свободно из 115 GB |
| Память / swap | 8 GB RAM (7.3 GB available); 2 GB zram swap, не используется |
| Температура | 59.3°C в момент инвентаризации |
| Docker | Docker 29.8.0, Compose 5.5.1, overlayfs; data-root `/var/lib/docker` |
| Существующие контейнеры | Только `sing-box` (host network, restart `unless-stopped`, конфиг `/home/bimo/sing-box/config.json` read-only) |
| OpenClaw | Не найден: нет контейнера, volume, network или каталога с таким именем |
| PostgreSQL / Redis | Нет контейнеров; Docker volumes и пользовательские Docker networks отсутствуют |

## Выполнено

1. Проверена доступность Raspberry Pi Connect и устройства.
2. Подтверждены модель, RAM, ОС и архитектура через Connect.
3. Подтверждена сетевая доступность TCP/22 через Tailscale.
4. Подтверждён ключевой доступ как `bimo` с отдельным Ed25519-ключом; пользователь состоит в группах `sudo` и `docker`.
5. Проведена read-only инвентаризация ОС, CPU, RAM, дисков, температуры, Docker, сервисов, Tailscale, Git, Python и каталогов приложений.
6. Подтверждена изоляция: `sing-box` — единственный существующий Docker workload; он не будет изменяться.
7. Scaffold развёрнут в `/opt/neuro-lab`; секретный `.env` создан на Pi с правами `0600`, владельцем `bimo`, и исключён из Git.
8. Запущен изолированный Compose project `neuro-lab`: PostgreSQL 17, Redis 7 и orchestrator worker.
9. Healthchecks PostgreSQL и Redis успешны. Smoke-test `Redis → worker → PostgreSQL` завершился `succeeded`, создан один нулевой `cost_event`; внешние API не вызывались.
10. После запуска вновь проверен `sing-box`: он `running`, работает в `host` network и имеет прежний `StartedAt` — никаких действий над ним не выполнялось.
11. Добавлен GigaChat provider adapter с двумя явными credential lanes: `primary` (пакетный ключ) и `freemium` (бесплатный ключ). OpenRouter намеренно не реализован и выключен.
12. В образ worker добавлен корневой сертификат НУЦ Минцифры только для этого контейнера; TLS-проверка включена, системное trust store Pi не менялось.
13. Подтверждены обе GigaChat-линии реальными минимальными запросами через `GigaChat-2-Pro`: primary и freemium вернули `READY`, каждая записала 27 prompt + 3 completion tokens в PostgreSQL. OpenRouter не вызывался.
14. Реальный каталог первого ключа содержит 10 моделей: шесть chat и четыре embedder. Каждая проверена минимальным вызовом через primary lane и успешно записана в PostgreSQL.
15. Добавлена операция `embeddings`, воспроизводимый `probe_models.py`, сохранение безопасного текста ошибок и retry/backoff для HTTP 429 и временных 5xx.
16. Собрана и запущена web-панель `neuro-lab-dashboard`: состояние Pi, четыре сервиса, очередь, последние задачи, usage и безопасная форма тестовой chat-задачи.
17. Панель слушает только `127.0.0.1:8080` на Pi. Она не имеет доступа к Docker socket или GigaChat-ключам; доступ к PostgreSQL и Redis ограничен необходимыми URL.
18. Добавлен изолированный `neuro-lab-monitor`: каждую минуту он сохраняет температуру, load, RAM и место на рабочем диске в PostgreSQL. Ретенция метрик — 30 дней.
19. Панель переработана: центральный SVG-график температуры имеет масштабы 1 час, 12 часов и сутки; вторичные показатели сделаны компактнее. API графика проверен на Pi, а отображение подтверждено через Tailscale Serve.

## Блокер

Нет. Ключевой SSH-доступ как `bimo` подтверждён.

## Предполагаемая архитектура

```text
                 Tailscale / SSH / Pi Connect
                            |
                    Raspberry Pi 5
                            |
        /opt/neuro-lab (Git-tracked config + app)
                            |
  docker compose project: neuro-lab (isolated)
       |              |                |
  PostgreSQL       Redis        orchestrator workers
  tasks/events     queue        API job execution
       |              |                |
       +--------- cost events --------+
                            |
                   monitor (1-minute samples)
                            |
            /srv/neuro-lab (mutable data)
              logs / cache / artifacts

After NVMe:
  /var/lib/docker, PostgreSQL volume, Redis volume,
  /srv/neuro-lab -> NVMe mount (e.g. /mnt/nvme/neuro-lab)
```

## Файлы scaffold

- `rpi5-control-plane/compose.yaml` — isolated PostgreSQL, Redis и orchestrator.
- `rpi5-control-plane/.env.example` — безопасные параметры-заглушки.
- `rpi5-control-plane/orchestrator/` — минимальный worker и schema для task/cost/event tracking.
- `rpi5-control-plane/scripts/inventory.sh` — только чтение, безопасная инвентаризация.
- `rpi5-control-plane/scripts/bootstrap.sh` — создаёт каталоги и проверяет Docker; фактический запуск требует `--apply`.
- `rpi5-control-plane/scripts/nvme-migration-plan.sh` — выводит план переноса, ничего не меняет.

## Развёрнуто на Pi

```text
/opt/neuro-lab/
  compose.yaml, .env (0600), PROJECT_PLAN.md, postgres/, orchestrator/, scripts/
/srv/neuro-lab/
  logs/, cache/, artifacts/
Docker project: neuro-lab
  neuro-lab-postgres-1      healthy, internal 5432/tcp only
  neuro-lab-redis-1         healthy, internal 6379/tcp only
  neuro-lab-orchestrator-1  running
  neuro-lab-orchestrator-2  running
  neuro-lab-monitor-1       running, minute host metrics
  neuro-lab-dashboard-1     loopback-only 127.0.0.1:8080
```

PostgreSQL и Redis не публикуют порт на хост: контейнерные `5432/tcp` и `6379/tcp` доступны только участникам `neuro-lab-control-plane`.

Исключение — dashboard намеренно публикует HTTP только на `127.0.0.1:8080`, то есть он недоступен из LAN/интернета. После однократного подтверждения в Tailscale он будет отдан как приватный HTTPS-сервис через Tailscale Serve, доступный только tailnet.

## Web-панель

Панель находится в `rpi5-control-plane/dashboard/` и развёрнута в `/opt/neuro-lab/dashboard/`.

- Центральный график температуры строится из минутных samples PostgreSQL. Кнопки `1 час`, `12 часов`, `сутки` меняют окно без перезагрузки; у истории ограничение 30 дней, поэтому microSD не получает бесконечный поток данных.
- Показывает также компактные load, свободное место, очередь, два worker'а, последние задачи и usage за 24 часа.
- Из ответов API удаляются embedding vectors: отображается только размерность, поэтому UI не передаёт многотысячные массивы данных браузеру.
- Форма принимает только известные chat-модели, ограничивает prompt до 8 000 символов и `max_tokens` до 2 048. Линия credentials выбирается явно; по умолчанию выбран Freemium.
- Tailscale Serve ещё ожидает включения в tailnet. Funnel не используется и публичный интернет-доступ не создаётся.
- Tailscale Serve включён и проксирует только `https://<private Tailnet hostname>/` → `http://127.0.0.1:8080`. Проверка с другого устройства tailnet успешна. Для отключения: `sudo tailscale serve --https=443 off`.

## GigaChat policy

- `credential_lane: "primary"` использует `GIGACHAT_KEY_A1` — ключ с платными пакетами. Это маршрут по умолчанию.
- `credential_lane: "freemium"` использует `GIGACHAT_KEY_L1` — отдельная Freemium-линия.
- Два worker’а обслуживают очередь параллельно; выбор линии задаётся в task payload, а не определяется по содержимому ключа.
- `GIGACHAT_API_PERS` используется для OAuth. OAuth endpoint — `https://ngw.devices.sberbank.ru:9443/api/v2/oauth`; запросы модели идут на `https://api.giga.chat/v1`.
- OpenRouter отключён (`OPENROUTER_ENABLED=false`) и не имеет adapter-а, поэтому не может быть использован случайно.
- Стоимость в USD для GigaChat не подставляется искусственно: сохраняются фактические usage tokens и имя линии; учёт пакетов остаётся в кабинете GigaChat.

## Возможности первого GigaChat-ключа, подтверждённые API

Актуальный `GET /v1/models` первого ключа вернул десять моделей. Ниже не теоретический перечень: 13 сентября 2026 года каждая модель получила отдельный минимальный запрос через `credential_lane: primary`.

| Модель запроса | Тип | Фактический результат |
| --- | --- | --- |
| `GigaChat-2` | chat | `GigaChat-2:2.0.30.01`, `OK` |
| `GigaChat-2-Max` | chat | `GigaChat-2-Max:2.0.30.01`, `OK` |
| `GigaChat-2-Pro` | chat | `GigaChat-2-Pro:2.0.30.01`, `OK` |
| `GigaChat-3-Lightning` | chat | `GigaChat-3-Lightning:32.4.16.3`, `OK` |
| `GigaChat-3-Pro` | chat | `GigaChat-3-Pro:32.4.30.3`, `OK` |
| `GigaChat-3-Ultra` | chat | `GigaChat-3-Ultra:32.9.23.6`, `OK` |
| `Embeddings` | embedder | вектор 1024 |
| `Embeddings-2` | embedder | API вернул имя `Embeddings2`, вектор 1024 |
| `EmbeddingsGigaR` | embedder | вектор 2560 |
| `GigaEmbeddings-3B-2025-09` | embedder | вектор 2048 |

Первый массовый probe дал пять временных HTTP 429 из-за двух worker'ов и одновременного старта десяти запросов. После добавления ограниченных повторов с backoff все пять прошли; итог — 10/10 успешных моделей. Исторические failed-записи первого прогона намеренно сохранены для аудита.

Поддерживаемые task payload:

```json
{
  "provider": "gigachat",
  "operation": "chat",
  "credential_lane": "primary",
  "model": "GigaChat-3-Pro",
  "messages": [{"role": "user", "content": "Задача"}]
}
```

```json
{
  "provider": "gigachat",
  "operation": "embeddings",
  "credential_lane": "primary",
  "model": "GigaEmbeddings-3B-2025-09",
  "input": ["первый текст", "второй текст"]
}
```

## Следующие действия на Pi

1. Добавить ограничение логов/backup policy до начала интенсивной работы с microSD.
2. Подтвердить Tailscale Serve и проверить приватный HTTPS-доступ к dashboard с устройства tailnet.
3. Реализовать отдельный режим `web-research`: поиск внешним провайдером с сохранением URL, выдержек и стоимости, затем передача только найденного контекста в GigaChat для синтеза. До выбора и явного разрешения провайдера он не включается.
4. Добавить планировщик и API приёма задач поверх уже проверенных chat/embeddings операций.
5. После прихода NVMe: смонтировать по UUID, остановить только `neuro-lab`, перенести его mutable data, обновить mount bindings и проверить восстановление.

## Риски и контроль

| Риск | Контроль |
| --- | --- |
| Изменение существующего OpenClaw или sing-box | Только read-only инвентаризация до явного анализа; проект и volume names изолированы. `sing-box` считается критичным и не является целью операций. |
| Износ/переполнение microSD | Ограничить логи, не разворачивать тяжёлые образы/данные до NVMe; проверять `df` перед запуском. |
| Рост истории мониторинга | Метрики пишутся раз в минуту и автоматически удаляются после 30 дней; при переносе на NVMe срок хранения можно увеличить. |
| Секреты в Git или логах | `.env` исключён; выводы диагностик не содержат env/ключи. |
| Нежелательные расходы OpenRouter | Маршрут выключен; для web-research потребуется отдельное явное включение и лимиты на задачу/день. |
| Сбой при NVMe migration | compose/config остаются в Git; мигрировать только mutable data с остановкой исключительно `neuro-lab`. |
| Неподтверждённая SSH-аутентификация | Не подбирать пользователей/пароли и не менять `sshd` до предоставления доступа. |

## Команды выполнения после доступа

```bash
sudo install -d -m 0750 /opt/neuro-lab /srv/neuro-lab/{logs,cache,artifacts}
cd /opt/neuro-lab
bash scripts/inventory.sh | tee inventory/initial-$(date +%F).txt
bash scripts/bootstrap.sh                 # только проверки и создание каталогов
# после проверки отчёта:
bash scripts/bootstrap.sh --apply
docker compose --env-file .env up -d
docker compose ps
```

Не выполнять `docker compose down -v`, `docker system prune`, `rm -rf`, перенос `/var/lib/docker` или изменения systemd до инвентаризации и отдельной сверки путей.
