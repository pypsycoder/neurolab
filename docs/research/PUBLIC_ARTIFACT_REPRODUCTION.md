# Воспроизведение публичного исследовательского артефакта

Этот контур предназначен только для открытого IT-исследования и synthetic
fixtures. Он не получает клинические данные, `.env`, Docker socket, основную
рабочую копию НейроЛаба или право менять/публиковать код.

## Необходимая цепочка доказательств

Запуск внешнего кода возможен только после всех пунктов ниже:

1. У публикации есть явная ссылка на артефакт, подтверждённая человеком.
2. Существует human-reviewed claim с page-located evidence и тем же
   `source_key`.
3. Bounded GitHub verifier сохранил metadata receipt: публичность, SPDX
   license, default branch, README, тесты и manifest среды.
4. Отдельный import step получил неизменяемый snapshot по конкретному commit
   hash и проверил его SHA-256. Нельзя брать `main` или произвольный URL.
5. Человек утвердил точную test/reproduction команду и лимиты.

Ни один из этих сигналов сам по себе не доказывает, что опубликированный
результат воспроизводится.

## Исполнительная граница

`scripts/verify_disposable_reproduction_sandbox.sh` подтверждает границу на
версируемой synthetic fixture. Он требует явный opt-in, создаёт временный
каталог в ignored `runtime/`, запускает тест только в disposable Docker
container с `--network none`, read-only root filesystem, непривилегированным
UID, drop всех capabilities, `no-new-privileges`, `pids-limit` и bounded tmpfs.
После завершения рабочая область удаляется.

Это **не** запуск Flowcept и не evidence of reproduction. Он проверяет, что
будущий evaluator не начинает с доверия к внешнему коду. Внешний snapshot
появится лишь как отдельный review-approved step после выполнения всей цепочки
доказательств выше. Результат такого запуска должен записываться как
`reproduced`, `partially_reproduced`, `failed` или `not_evaluated` вместе с
commit SHA, image digest, точной командой, ограничениями и redacted failure
receipt; он не повышает готовность клинического контура.
