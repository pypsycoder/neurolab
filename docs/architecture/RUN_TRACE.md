# Synthetic run trace

`neurolab.run_trace` создаёт только детерминированную metadata-запись для
local-only synthetic smoke: hashed run ID, версии graph/prompt contract,
решение, latency, safe audit labels и относительную ссылку на документацию.

В trace запрещены prompt, model output, content источников, абсолютные пути,
path traversal, `.env`, значения секретов и идентификатор потока в открытом
виде. Любой неподходящий label, decision, metric или artifact reference
отклоняется до создания отчёта.

Это проверяемый in-memory contract, а не persistent observability storage,
не provider telemetry и не clinical audit log.
