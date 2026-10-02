#!/usr/bin/env bash
# Narrow, opt-in boot-parameter change. Does not reboot or change networking.
# Raspberry Pi maintainer explanation: linux/issues/6980#issuecomment-3149752155.
set -euo pipefail
[[ "${ENABLE_RP5_MEMORY_CGROUP:-0}" == 1 ]] || { echo 'Set ENABLE_RP5_MEMORY_CGROUP=1'; exit 2; }
[[ "$(id -u)" == 0 && "$(uname -m)" == aarch64 ]] || exit 2
TARGET=/boot/firmware/cmdline.txt
[[ -f "$TARGET" && ! -L "$TARGET" ]] || exit 2
# Preserve every existing root/mount/network parameter. Require one boot line.
[[ "$(awk 'END {print NR}' "$TARGET")" == 1 ]] || exit 2
grep -q 'root=' "$TARGET" || exit 2
if grep -qw 'cgroup_enable=memory' "$TARGET"; then
  echo 'memory_cgroup: parameter already present; inspect runtime after reboot'
  exit 0
fi
BACKUP="/boot/firmware/cmdline.txt.neurolab-backup-$(date -u +%Y%m%dT%H%M%SZ)"
[[ ! -e "$BACKUP" ]] || exit 2
cp -- "$TARGET" "$BACKUP"
sed -i 's/$/ cgroup_enable=memory/' "$TARGET"
grep -qw 'cgroup_enable=memory' "$TARGET"
echo "memory_cgroup: parameter appended; original preserved at $BACKUP; reboot required"
