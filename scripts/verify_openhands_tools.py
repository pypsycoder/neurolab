#!/usr/bin/env python3
"""Opt-in offline probe of the exact pinned OpenHands CLI and isolated mounts."""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from uuid import uuid4

from run_experimental_code import CLI_SHA, IMAGE, ROOT, command, require


def main():
    if os.environ.get("RUN_OPENHANDS_TOOL_PROBE") != "1" or os.name != "posix" or os.geteuid() != 0:
        raise ValueError("opt-in root Docker coordinator required")
    cli = ROOT / "runtime/openhands-eval/bin/openhands-1.16.0-linux-arm64"
    if sha256(cli.read_bytes()).hexdigest() != CLI_SHA:
        raise ValueError("pinned CLI checksum mismatch")
    root = (ROOT / "runtime/it-research").resolve()
    run_id = str(uuid4()); suffix = run_id.replace("-", "")[:16]
    network = "nl-tool-probe-" + suffix
    server = "nl-tool-server-" + suffix; agent = "nl-tool-client-" + suffix
    work = Path(tempfile.mkdtemp(prefix="tool-probe-", dir=root)); work.chmod(0o755)
    workspace = work / "workspace"; workspace.mkdir(mode=0o755)
    experiment = workspace / "experiment"; experiment.mkdir(mode=0o700); os.chown(experiment, 1000, 1000)
    probe = experiment / "probe.txt"; probe.write_text("before\n"); probe.chmod(0o600); os.chown(probe, 1000, 1000)
    receipt = {"run_id": run_id, "status": "failed", "agent": "OpenHands-CLI-1.16.0", "sdk": "1.21.0",
               "boundary": "offline_synthetic_tool_probe", "real_model_calls": 0, "credentials_mounted": False,
               "raw_content_retained": False, "production_deployed": False}
    security = ["--read-only", "--log-driver", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "64", "--cpus", "2"]
    try:
        require(["docker", "network", "create", "--internal", network])
        require(["docker", "run", "--rm", "-d", "--name", server, "--network", network, "--network-alias", "tool-fixture",
                 *security, "--memory", "128m", "--user", "1000:1000", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                 "-v", f"{ROOT / 'tests/fixtures/openhands_tool_server.py'}:/fixture.py:ro", "--entrypoint", "/usr/local/bin/python", IMAGE, "-B", "/fixture.py"])
        time.sleep(1)
        # Same read-only parent + writable experiment layout as the code runner.
        # Verify non-root access before involving the official editor.
        access, _ = command(["docker", "run", "--rm", "--network", "none", "--user", "1000:1000", *security, "--memory", "128m",
            "-v", f"{workspace}:/workspace:ro", "-v", f"{experiment}:/workspace/experiment:rw", "--entrypoint", "/usr/local/bin/python", IMAGE, "-B", "-c",
            "from pathlib import Path; p=Path('/workspace/experiment/probe.txt'); assert p.read_text()=='before\\n'; p.write_text('before\\n'); "
            "assert not __import__('os').access('/workspace',__import__('os').W_OK)"])
        receipt["mount_access_passed"] = access == 0
        if access != 0:
            raise ValueError("isolated mount access failed")
        events = {}
        code, _ = command(["docker", "run", "--rm", "--name", agent, "--network", network, "--user", "1000:1000",
            *security, "--memory", "2g", "--memory-swap", "2g", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--tmpfs", "/home/agent:rw,nosuid,size=32m,uid=1000,gid=1000", "--tmpfs", "/tmp/agent-runtime:rw,exec,nosuid,size=256m,uid=1000,gid=1000",
            "-e", "HOME=/home/agent", "-e", "TMPDIR=/tmp/agent-runtime", "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "OPENHANDS_SUPPRESS_BANNER=1",
            "-e", "LLM_API_KEY=offline-probe-not-a-secret", "-e", "LLM_BASE_URL=http://tool-fixture:8090/v1", "-e", "LLM_MODEL=openai/GigaChat-2-Pro",
            "-v", f"{cli}:/openhands:ro", "-v", f"{workspace}:/workspace:ro", "-v", f"{experiment}:/workspace/experiment:rw",
            "-w", "/workspace/experiment", "--entrypoint", "/openhands", IMAGE, "--headless", "--json", "--always-approve", "--exit-without-confirmation", "--override-with-envs",
            "--task", "Offline tool protocol probe. Edit only /workspace/experiment/probe.txt: replace before with after, then finish."], timeout=180, events=events)
        command(["docker", "rm", "-f", agent])
        receipt.update(agent_exit_code=code, agent_event_counts=events, file_changed=probe.read_text() == "after\n")
        if code == 0 and receipt["file_changed"]:
            receipt["status"] = "passed"
    finally:
        for name in (agent, server):
            command(["docker", "rm", "-f", name])
        command(["docker", "network", "rm", network])
        if work.parent != root or not work.name.startswith("tool-probe-"):
            raise ValueError("unsafe probe cleanup")
        shutil.rmtree(work)
        path = root / f"tool-probe-receipt-{run_id}.json"; path.write_text(json.dumps(receipt, sort_keys=True) + "\n"); path.chmod(0o600)
        print(json.dumps(receipt, sort_keys=True))
    if receipt["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("offline_tool_probe_failed: no raw diagnostics retained") from None
