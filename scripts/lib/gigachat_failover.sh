#!/usr/bin/env bash
# Shared two-lane GigaChat failover for public/synthetic research calls.
# It never prints credentials, captured provider bodies, prompts, or responses.

set -o pipefail

_gigachat_pause_file() { printf '%s/runtime/it-research/gigachat-rate-limit-pause-until\n' "$1"; }

_gigachat_is_paused() {
  local root="$1" pause_file now until
  pause_file="$(_gigachat_pause_file "$root")"
  [[ -f "$pause_file" ]] || return 1
  until="$(head -n 1 "$pause_file" 2>/dev/null || true)"
  now="$(date -u +%s)"
  [[ "$until" =~ ^[0-9]+$ && "$now" -lt "$until" ]]
}

_gigachat_record_pause() {
  local root="$1" pause_file until
  pause_file="$(_gigachat_pause_file "$root")"
  mkdir -p "$(dirname "$pause_file")"
  until="$(( $(date -u +%s) + ${NEUROLAB_GIGACHAT_PAUSE_SECONDS:-900} ))"
  printf '%s\n' "$until" > "$pause_file"
}

_gigachat_load_model() {
  local env_file="$1" python_bin="$2"
  NEUROLAB_ENV_FILE="$env_file" "$python_bin" -c '
import os, re
from dotenv import dotenv_values
value = dotenv_values(os.environ["NEUROLAB_ENV_FILE"]).get("GIGACHAT_MODEL", "GigaChat-2-Pro")
if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{2,80}", value.strip()):
    raise SystemExit("Configured GigaChat model is invalid.")
print(value.strip())
'
}

_gigachat_load_credential() {
  local lane="$1" env_file="$2" python_bin="$3" config_name
  case "$lane" in
    primary) config_name="GIGACHAT_PRIMARY_KEY_ENV" ;;
    freemium) config_name="GIGACHAT_FREEMIUM_KEY_ENV" ;;
    *) echo "Unsupported GigaChat credential lane." >&2; return 2 ;;
  esac
  NEUROLAB_ENV_FILE="$env_file" NEUROLAB_GIGACHAT_CONFIG_NAME="$config_name" "$python_bin" -c '
import os
from dotenv import dotenv_values
values = dotenv_values(os.environ["NEUROLAB_ENV_FILE"])
config_name = os.environ["NEUROLAB_GIGACHAT_CONFIG_NAME"]
name = values.get(config_name)
if not isinstance(name, str) or not name.isidentifier():
    raise SystemExit("Configured GigaChat credential name is invalid.")
value = values.get(name)
if not value:
    raise SystemExit("Configured GigaChat credential is absent or empty.")
print(value)
'
}

_gigachat_is_transient_failure() {
  grep -Eq '(^|[^0-9])429([^0-9]|$)|RateLimitError|ConnectTimeout|TimeoutError|temporarily unavailable' <<<"$1"
}

gigachat_run_with_failover() {
  # runner arguments: lane credential model followed by the caller's arguments.
  local root="$1" env_file="$2" python_bin="$3" runner="$4"
  shift 4
  local model lane credential captured status
  if _gigachat_is_paused "$root"; then
    echo "GigaChat research lanes are paused after rate limiting; no provider call was made." >&2
    return 75
  fi
  model="$(_gigachat_load_model "$env_file" "$python_bin")" || return $?
  for lane in primary freemium; do
    credential="$(_gigachat_load_credential "$lane" "$env_file" "$python_bin")" || {
      echo "Configured GigaChat $lane lane is unavailable." >&2
      return 1
    }
    if captured="$("$runner" "$lane" "$credential" "$model" "$@" 2>&1)"; then
      printf '%s\n' "$captured"
      unset credential
      return 0
    fi
    status=$?
    unset credential
    if ! _gigachat_is_transient_failure "$captured"; then
      echo "GigaChat $lane lane failed without an eligible failover." >&2
      return "$status"
    fi
    if [[ "$lane" == "primary" ]]; then
      echo "GigaChat primary lane is rate-limited; switching once to freemium." >&2
      continue
    fi
    _gigachat_record_pause "$root"
    echo "Both GigaChat lanes are temporarily limited; research calls are paused for 15 minutes." >&2
    return 75
  done
}
