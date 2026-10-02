#!/usr/bin/env python3
"""Read-only, redacted inventory. No provider calls, credentials, or payloads."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.request import urlopen


def command(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(args, input=stdin, text=True, capture_output=True, timeout=30, check=True)
    return result.stdout.strip()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if Path.cwd().resolve() != root:
        raise SystemExit("Run from the repository root")
    report: dict[str, object] = {"version": "rp5-health-v1", "synthetic_only": True}
    report["git_head"] = command("git", "rev-parse", "HEAD")
    report["worktree_paths"] = command("git", "status", "--short").splitlines()
    services_raw = command("sudo", "-n", "docker", "compose", "ps", "--format", "json")
    services = json.loads(services_raw) if services_raw.startswith("[") else [json.loads(line) for line in services_raw.splitlines()]
    report["services"] = [{key: row.get(key) for key in ("Service", "State", "Health", "ExitCode")} for row in services]
    report["resources"] = command("sudo", "-n", "docker", "info", "--format", "cgroup={{.CgroupVersion}} memory_limit={{.MemoryLimit}} pids_limit={{.PidsLimit}}")
    report["env_readable_by_owner"] = (root / ".env").is_file() and (root / ".env").stat().st_uid == 1000
    report["database"] = json.loads(command(
        "sudo", "-n", "docker", "compose", "exec", "-T", "postgres", "sh", "-c",
        'psql -X -tA -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
        stdin="""SELECT json_build_object(
          'migrations', (SELECT count(*) FROM schema_migrations),
          'sources', (SELECT count(*) FROM it_research.sources),
          'documents', (SELECT count(*) FROM it_research.documents),
          'document_cards', (SELECT count(*) FROM it_research.document_cards),
          'diagram_cards', (SELECT count(*) FROM it_research.diagram_cards),
          'tasks', (SELECT count(*) FROM tasks),
          'running_tasks', (SELECT count(*) FROM tasks WHERE status = 'running'));
        """))
    with urlopen("http://127.0.0.1:8080/", timeout=10) as response:
        report["dashboard_http"] = response.status
    report["backups"] = command("sudo", "-n", "find", "/srv/neuro-lab/backups", "-maxdepth", "1", "-type", "f", "-printf", "%f %s bytes\n").splitlines()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("rp5_healthcheck_failed: check unavailable; no raw diagnostics emitted") from None
