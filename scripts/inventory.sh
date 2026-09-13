#!/usr/bin/env bash
set -euo pipefail

section() { printf '\n===== %s =====\n' "$1"; }
section "host"; hostnamectl || hostname
section "os"; cat /etc/os-release
section "kernel"; uname -a
section "cpu"; lscpu || true
section "memory"; free -h
section "storage"; lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS,MODEL,SERIAL
section "filesystems"; df -hT
section "temperature"; vcgencmd measure_temp 2>/dev/null || cat /sys/class/thermal/thermal_zone0/temp || true
section "docker versions"; docker --version 2>&1 || true; docker compose version 2>&1 || true
section "docker containers"; docker ps -a --no-trunc 2>&1 || true
section "docker images"; docker image ls 2>&1 || true
section "docker volumes"; docker volume ls 2>&1 || true
section "docker networks"; docker network ls 2>&1 || true
section "services"; systemctl --no-pager --type=service --state=running 2>&1 || true
section "tailscale"; tailscale status 2>&1 || true
section "git/python"; git --version 2>&1 || true; python3 --version 2>&1 || true
section "likely application paths"; find /opt /srv /home -maxdepth 3 -type d \( -iname '*openclaw*' -o -iname '*docker*' -o -iname '*neuro*' \) -print 2>/dev/null || true
