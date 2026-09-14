"""Opt-in E2E test for the one-off, read-only MCP fixture container on RP5."""

import asyncio
import os
from pathlib import Path
import shutil
import unittest

from mcp import Client, StdioServerParameters


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_DOCKER_EVAL = os.environ.get("RUN_MCP_DOCKER_EVAL") == "1"


@unittest.skipUnless(RUN_DOCKER_EVAL and shutil.which("docker"), "opt-in RP5 Docker MCP evaluation")
class McpDockerFixtureTests(unittest.TestCase):
    def test_container_reads_only_the_synthetic_fixture_and_rejects_traversal(self):
        async def exercise_server() -> None:
            parameters = StdioServerParameters(
                command="docker",
                args=[
                    "run", "--rm", "-i", "--network", "none", "--read-only",
                    "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges", "--user", "65534:65534",
                    "-e", "PYTHONPATH=/opt/venv/lib/python3.13/site-packages:/app/src",
                    "-v", f"{PROJECT_ROOT / 'runtime' / 'langgraph-eval'}:/opt/venv:ro",
                    "-v", f"{PROJECT_ROOT / 'src'}:/app/src:ro",
                    "-v", f"{PROJECT_ROOT / 'tests' / 'fixtures' / 'mcp-repository'}:/fixtures:ro",
                    "--entrypoint", "python3", "neurolab/gpt2giga-eval:v0.3.0",
                    "-m", "neurolab.mcp_fixture_server",
                ],
            )
            async with Client(parameters) as client:
                tools = await client.list_tools()
                self.assertEqual([tool.name for tool in tools.tools], ["test.fixture.read"])

                allowed = await client.call_tool(
                    "test.fixture.read", {"path": "fixtures/synthetic-source.md"}, read_timeout_seconds=5
                )
                self.assertFalse(allowed.is_error)
                self.assertIn("Synthetic MCP fixture", allowed.content[0].text)
                self.assertIn('"trusted":false', allowed.content[0].text.replace(" ", ""))

                blocked = await client.call_tool(
                    "test.fixture.read", {"path": "fixtures/../.env"}, read_timeout_seconds=5
                )
                self.assertTrue(blocked.is_error)
                self.assertIn("blocked by policy", blocked.content[0].text)

        asyncio.run(exercise_server())
