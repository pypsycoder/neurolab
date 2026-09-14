"""End-to-end test of the isolated local MCP stdio transport."""

import asyncio
from pathlib import Path
import sys
import unittest

from mcp import Client, StdioServerParameters


class McpStdioTests(unittest.TestCase):
    @staticmethod
    def _parameters() -> StdioServerParameters:
        source_root = Path(__file__).resolve().parents[1] / "src"
        return StdioServerParameters(
            command=sys.executable,
            args=["-m", "neurolab.mcp_test_server"],
            env={"PYTHONPATH": str(source_root)},
        )

    def test_server_advertises_only_test_tools_and_returns_untrusted_data(self):
        async def exercise_server() -> None:
            async with Client(self._parameters()) as client:
                tools = await client.list_tools()
                self.assertEqual(
                    {tool.name for tool in tools.tools},
                    {"test.docs.lookup", "test.fixture.read", "test.git.diff"},
                )
                result = await client.call_tool(
                    "test.docs.lookup", {"query": "synthetic LangGraph evidence"}, read_timeout_seconds=5
                )
                self.assertFalse(result.is_error)
                self.assertIn("synthetic MCP result: test.docs.lookup", result.content[0].text)
                self.assertIn('"trusted":false', result.content[0].text.replace(" ", ""))

        asyncio.run(exercise_server())

    def test_server_rejects_forbidden_paths_and_extra_arguments_over_stdio(self):
        async def exercise_server() -> None:
            async with Client(self._parameters()) as client:
                traversal = await client.call_tool(
                    "test.fixture.read", {"path": "fixtures/../.env"}, read_timeout_seconds=5
                )
                self.assertTrue(traversal.is_error)
                self.assertIn("blocked by policy", traversal.content[0].text)

                extra_argument = await client.call_tool(
                    "test.docs.lookup",
                    {"query": "safe", "url": "https://example.invalid"},
                    read_timeout_seconds=5,
                )
                self.assertTrue(extra_argument.is_error)

        asyncio.run(exercise_server())
