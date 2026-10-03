# Развёртывание на Raspberry Pi 5

**Цель:** Raspberry Pi 5 — единственная среда выполнения `dev/test` НейроЛаба.
Точные реквизиты доступа хранятся только в локальном `docs/private/RP5_ACCESS.md`
и исключены из Git, потому что репозиторий публичный.

## Подтверждённая исходная среда

- Raspberry Pi 5, 8 GB RAM, Raspberry Pi OS 13 (arm64).
- Доступ через Tailscale и SSH подтверждён в предыдущей инвентаризации.
- На устройстве уже работает **основной стек НейроЛаба** — Docker Compose
  проект `neuro-lab` в `/opt/neuro-lab` с PostgreSQL, Redis, orchestrator,
  monitor и dashboard. Он является целевой рабочей копией проекта.
- После замены накопителя внешний трафик обеспечивается постоянным Throne
  SSH/VPS tunnel, Tailscale использует восстановленный proxy profile.
  `sing-box` не активен; не переносить старые предположения на новый runtime.
  Ни один из сетевых сервисов не является целью операций NeuroLab rollout.

## Привязка GitHub к существующей рабочей копии

Сначала выполнить только read-only инвентаризацию `/opt/neuro-lab`: Git remote,
ветку, рабочее дерево, Compose state и наличие локального `.env`. Лишь после
этого подключить `https://github.com/pypsycoder/neurolab.git` как `origin` и
согласовать историю без перезаписи существующих файлов или секретов.

```bash
cd /opt/neuro-lab
git status --short
git remote -v
git branch --show-current
docker compose ps
```

## Секреты и живая проверка

Реальные значения ключей остаются только в уже существующем локальном env-файле
на Pi, с правами доступа владельца. Их нельзя копировать в Git, чат, логи или
файлы тестов. Для live-проверки указывается путь к этому файлу:

```bash
NEUROLAB_ENV_FILE=/локальный/путь/.env ./scripts/verify_gigachat_live.sh
```

Скрипт делает только запрос списка моделей. Он не отправляет пациентские данные
и не выводит ключ.

## Проверка перед изменениями

Перед развёртыванием выполнить read-only проверку: версия Git/Python, свободное
место, статус Tailscale и отсутствие конфликта имён каталогов/Compose-проектов.
Любая работа с Docker, systemd, `sing-box`, ключами или секретными `.env` —
только после отдельной проверки и явной необходимости. Не выполнять `git
reset`, `git clean`, `docker compose down`, `docker system prune` или замену
`.env` при подключении GitHub.

## Восстановленный runtime (2026-10-02)

RP5: Python 3.13, Docker/Compose, NVMe ext4. Секреты в `/opt/neuro-lab/.env`
0600, владелец bimo; значения не копируются на Windows или в Git.
Research — opt-in Compose profile, официальный GigaChat SDK; CA bundle
создаётся `scripts/prepare_research_ca.sh` только в ignored runtime.
OpenHands CLI 1.16.0 ARM64 + gpt2giga 0.3.0 восстанавливаются
`scripts/install_engineering_runtime.sh` с проверкой release checksum.

После точечного включения `cgroup_enable=memory` и проверенного reboot Docker
обеспечивает memory limit. Code runner проверяет реальный `memory.max` перед
исполнением; при отсутствии контроля памяти запуск запрещается.
Тесты readonly и не монтируются агенту, evaluator network-none;
agent имеет доступ только к ephemeral GigaChat proxy, не к host env/socket.

Определённые команды доступны только в synthetic-only контуре:

```bash
cd /opt/neuro-lab
.venv/bin/python scripts/rp5_healthcheck.py
sudo env RUN_EXPERIMENTAL_SPEC=1 \
  NEUROLAB_SSL_CERT_FILE=/opt/neuro-lab/runtime/ca/ca-certificates.crt \
  bash scripts/run_experimental_spec.sh
sudo env RUN_EXPERIMENTAL_CODE=1 bash scripts/run_experimental_code.sh \
  --spec /opt/neuro-lab/runtime/it-research/spec-<run-id>.json
```

Не запускать последний пример с placeholder: использовать существующий
receipt-backed run ID. Существующий `latest-spec-receipt.json` должен совпасть
с hash и ID спецификации. Raw agent transcripts не сохраняются; только
bounded validated spec, accepted candidate и machine receipts по policy.
Текущие результаты и дальнейшая работа — только в корневом `ROADMAP.md`.

`neurolab-backup.timer` включён; backup/restore проверяется в отдельной
disposable БД. Пока backup находится на том же NVMe: это не disk-failure
recovery. Off-device backup и непрерывный autonomous scheduler ещё не приняты.

## Durable receipt checkpoint (без model calls)

`run_durable_reconciliation.sh` использует официальный PostgresSaver 3.1.2.
`--setup` требуется только при первом создании checkpoint schema в
`it_research`; его таблицы/миграции управляются upstream, отдельно от
`schema_migrations` приложения. State содержит только bounded UUID/hash/
metrics/decision. Pickle/arbitrary module deserialization запрещены.

```bash
sudo env RUN_DURABLE_RECONCILIATION=1 bash scripts/run_durable_reconciliation.sh \
  --workflow-id <exact-workflow-uuid> --spec-run-id <exact-spec-uuid> \
  --code-run-id <exact-code-uuid> --setup --stop-after-spec
# В отдельном процессе: те же три UUID, но без --setup/--stop-after-spec.
# Незавершённый workflow можно отменить через --cancel.
```

Это receipt reconciliation, не генерация нового code/search и не paid
scheduler. Повтор terminal workflow ничего не вызывает/не переутверждает.
Для нового эксперимента обязателен новый workflow UUID; произвольная подмена
spec/code IDs для существующего checkpoint отклоняется.
