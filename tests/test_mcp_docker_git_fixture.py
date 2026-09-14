"""Opt-in E2E test for a real Git diff in the isolated MCP fixture container."""

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from mcp import Client, StdioServerParameters


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_DOCKER_EVAL = os.environ.get("RUN_MCP_DOCKER_EVAL") == "1"
_GIT_ENV = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}


def _run_git(arguments: list[str], repository: Path) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        env={**os.environ, **_GIT_ENV},
        text=True,
    )


@unittest.skipUnless(RUN_DOCKER_EVAL and shutil.which("docker"), "opt-in RP5 Docker MCP evaluation")
class McpDockerGitFixtureTests(unittest.TestCase):
    def test_container_returns_real_fixture_git_diff_and_rejects_other_ranges(self):
        with tempfile.TemporaryDirectory(prefix="neurolab-mcp-git-") as temporary_directory:
            repository = Path(temporary_directory) / "repository"
            Path(temporary_directory).chmod(0o755)
            shutil.copytree(PROJECT_ROOT / "tests" / "fixtures" / "mcp-git-repository", repository)
            _run_git(["init", "--quiet"], repository)
            _run_git(["config", "user.name", "NeuroLab MCP Test"], repository)
            _run_git(["config", "user.email", "mcp-test@example.invalid"], repository)
            _run_git(["add", "src/calculator.py"], repository)
            _run_git(["commit", "--quiet", "-m", "synthetic baseline"], repository)
            (repository / "src" / "calculator.py").write_text(
                "def add(left: int, right: int) -> int:\n    return left + right\n",
                encoding="utf-8",
            )

            async def exercise_server() -> None:
                parameters = StdioServerParameters(
                    command="docker",
                    args=[
                        "run", "--rm", "-i", "--network", "none", "--read-only",
                        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "--cap-drop", "ALL",
                        "--security-opt", "no-new-privileges", "--user", "65534:65534",
                        "--pids-limit", "64",
                        "-e", "PYTHONPATH=/opt/venv/lib/python3.13/site-packages:/app/src",
                        "-v", f"{PROJECT_ROOT / 'runtime' / 'langgraph-eval'}:/opt/venv:ro",
                        "-v", f"{PROJECT_ROOT / 'src'}:/app/src:ro",
                        "-v", f"{repository}:/repository:ro",
                        "-v", "/usr/bin/git:/usr/bin/git:ro",
                        "-v", "/usr/lib/git-core:/usr/lib/git-core:ro",
                        "--entrypoint", "python3", "neurolab/gpt2giga-eval:v0.3.0",
                        "-m", "neurolab.mcp_git_fixture_server",
                    ],
                )
                async with Client(parameters) as client:
                    tools = await client.list_tools()
                    self.assertEqual([tool.name for tool in tools.tools], ["test.git.diff"])

                    allowed = await client.call_tool(
                        "test.git.diff", {"base": "HEAD", "path": "src/calculator.py"}, read_timeout_seconds=5
                    )
                    self.assertFalse(allowed.is_error)
                    self.assertIn("-    return left - right", allowed.content[0].text)
                    self.assertIn("+    return left + right", allowed.content[0].text)
                    self.assertIn('"trusted":false', allowed.content[0].text.replace(" ", ""))

                    blocked = await client.call_tool(
                        "test.git.diff", {"base": "HEAD~1", "path": "src/calculator.py"}, read_timeout_seconds=5
                    )
                    self.assertTrue(blocked.is_error)
                    self.assertIn("blocked by policy", blocked.content[0].text)

            asyncio.run(exercise_server())
