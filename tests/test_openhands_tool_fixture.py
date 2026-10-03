import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("tool_fixture", Path(__file__).parent / "fixtures/openhands_tool_server.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class OfflineToolFixtureTests(unittest.TestCase):
    def test_replay_targets_only_the_probe_not_candidate(self):
        tools = [{"type": "function", "function": {"name": "file_editor"}}]
        name, action = fixture.tool_reply(tools, 0)
        self.assertEqual((name, action["command"], action["path"]), ("file_editor", "view", "/workspace/experiment/probe.txt"))
        name, action = fixture.tool_reply(tools, 1)
        self.assertEqual(action, {"command": "str_replace", "path": "/workspace/experiment/probe.txt", "old_str": "before", "new_str": "after", "security_risk": "LOW"})
        self.assertEqual(fixture.tool_reply(tools, 2)[0], "finish")

    def test_missing_official_editor_is_a_contract_failure(self):
        with self.assertRaises(ValueError):
            fixture.tool_reply([], 0)

    def test_negative_control_explicitly_omits_risk(self):
        with patch.dict("os.environ", {"TOOL_PROBE_OMIT_RISK": "1"}):
            _, action = fixture.tool_reply([{"type": "function", "function": {"name": "file_editor"}}], 1)
        self.assertNotIn("security_risk", action)
