# OpenHands: изолированная проверка 1.4

**Проверено:** 2026-09-14
**Режим:** техническая инженерная проба. Только синтетический код в
одноразовом Git-worktree; реальные пациенты, персональные данные, клинические
правила и production-секреты исключены.

## Выбор компонента

- Upstream CLI: [OpenHands/OpenHands-CLI](https://github.com/OpenHands/OpenHands-CLI).
- Проверенная ARM64-сборка: `1.16.0`.
- SHA-256 бинарного релизного артефакта сверялся с digest, опубликованным в
  GitHub release: `67c5cfb94e5fd4c4120eb0360b0f23337da31f64a70e8496bcf008e4caeea6af`.
- CLI сообщает `OpenHands CLI 1.16.0` и использует SDK `v1.21.0`.
- Upstream помечает этот CLI как не находящийся в активной разработке; перед
  расширением использования нужно повторно оценить поддерживаемый replacement.

## Обязательная изоляция

Headless-режим OpenHands автоматически одобряет действия. Поэтому он не
запускается на хосте RP5 и не получает основной checkout. Каждая проверка
создаёт отдельный worktree под `runtime/`, который Git игнорирует, и запускает
CLI в одноразовом Docker-container со следующими границами:

- Docker socket не монтируется, нет privileged-режима и все Linux capabilities
  сброшены;
- у контейнера нет общей сети: доступен только временный gpt2giga proxy во
  внутренней Docker-сети;
- в контейнер монтируются только проверяемый worktree и read-only бинарник;
- агент не видит `.env`, основной checkout, ключи, домашний каталог хоста или
  сервисы основного Compose-стека;
- proxy использует одноразовый ключ, а после проверки останавливается и его
  временный env-файл удаляется.

Ограничение RP5: Docker сообщил, что memory-limit capabilities ядра недоступны,
поэтому memory limit нельзя считать подтверждённой защитой. Изоляция опирается
на namespace/монтирования, отсутствие socket и сетевую сегментацию; ресурсные
лимиты требуют отдельной проверки при эксплуатации.

## Пройденный сценарий

В отдельной ветке `eval/openhands-small-fix` был создан небольшой синтетический
Python fixture с намеренной ошибкой: `add` выполняла вычитание. Headless
OpenHands через временный gpt2giga/GigaChat получил строго ограниченную задачу:
изменить только `openhands_eval_fixture/calculator.py`, выполнить
`python3 -m unittest discover -s openhands_eval_fixture` и не использовать
сеть, Docker, env или другие пути.

Фактический результат:

1. Agent process завершился с кодом `0`.
2. Единственный diff изменил `return left - right` на `return left + right`.
3. `unittest discover` завершился успешно: `1` test passed.
4. Основной Compose-стек не перезапускался; все шесть сервисов продолжили
   работать.
5. Временный proxy и одноразовый ключ были удалены. Worktree и redacted trace
   остаются только в ignored `runtime/` как проверяемый локальный артефакт.

## Границы роли

OpenHands может быть одноразовым Dev Agent для учебной или инженерной задачи в
изолированном worktree. Он не имеет права самостоятельно выполнять merge,
push, deploy, менять Compose, работать с пациентскими данными, медицинскими
правилами или клиническим контуром. Любая правка вне test-worktree требует
проверок, review и явного решения человека.

## Acceptance gate

`neurolab.engineering_policy.require_reviewable_change` — отдельный
проверяемый gate между sandboxed evaluator и человеком. Он принимает только
непустой diff в заранее заданном списке путей и успешный конкретный test
command. Результат всегда имеет решение `review_required`: gate не запускает
агента или команды, не выполняет merge/push/deploy и не считает правку
автоматически принятой.

Этот gate проверен только на synthetic metadata из уже подтверждённого
одноразового worktree. Повторный live OpenHands запуск требует отдельного
ручного решения и не входит в автоматический smoke.

## Повторяемый ручной synthetic runbook

`scripts/run_openhands_manual_eval.sh` запускается только при явном
`RUN_OPENHANDS_MANUAL_EVAL=1`. Он:

- читает local `.env` только как данные, берёт лишь указанный GigaChat
  credential и создаёт одноразовый proxy key;
- создаёт новый synthetic Git-worktree с заведомо падающим тестом;
- изолирует агента во внутренней Docker-сети: gpt2giga имеет отдельный
  upstream-network, агент видит лишь proxy, Docker socket и основной checkout
  не монтируются;
- даёт CLI только synthetic workspace, read-only root filesystem, capabilities
  dropped и tmpfs для HOME/cache/исполняемых временных библиотек PyInstaller;
- требует успешный независимый test, diff строго одного allowlisted файла и
  решение `review_required` от acceptance gate;
- удаляет proxy, сети, одноразовый env и worktree при любом завершении.

Фактический run 2026-09-14 прошёл: OpenHands исправил только
`openhands_eval_fixture/calculator.py`, его unit-test и независимая проверка
дали `1 passed`, а gate вернул `review_required`. Основной Compose-стек
остался в шести running-сервисах. Локальный redacted trace хранится только под
ignored `runtime/`; он не является артефактом для Git или клинического
контура.

## Следующий безопасный шаг

Собрать deterministic architectural smoke этапа E поверх уже подтверждённых
synthetic contracts. OpenHands-run остаётся ручным и approval-gated; для
research-пути по-прежнему действует ADR-0003: нужен trace поиска.
