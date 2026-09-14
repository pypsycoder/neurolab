"""End-to-end test of the isolated local MCP stdio transport."""

import asyncio
from pathlib import Path
import sys
import unittest

from mcp import Client, StdioServerParameters


class McpStdioTests(unittest.TestCase):
    def test_server_advertises_only_test_tools_and_returns_untrusted_data(self):
        async def exercise_server() -> None:
            source_root = Path(__file__).resolve().parents[1] / "src"
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "neurolab.mcp_test_server"],
                env={"PYTHONPATH": str(source_root)},
            )
            async with Client(parameters) as client:
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
