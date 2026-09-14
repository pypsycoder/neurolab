"""Test-only policy gate for future MCP tool integrations.

This module deliberately validates contracts before any transport or tool is
connected. MCP results remain untrusted data and never become instructions.
"""

from dataclasses import dataclass
import re
from typing import Any, Mapping


class McpPolicyError(ValueError):
    """A request is outside the explicitly approved test-only contract."""


@dataclass(frozen=True)
class ToolContract:
    name: str
    required: frozenset[str]
    allowed: frozenset[str]


CONTRACTS = {
    "test.docs.lookup": ToolContract("test.docs.lookup", frozenset({"query"}), frozenset({"query"})),
    "test.fixture.read": ToolContract("test.fixture.read", frozenset({"path"}), frozenset({"path"})),
    "test.git.diff": ToolContract("test.git.diff", frozenset({"base", "path"}), frozenset({"base", "path"})),
}

_FIXTURE_PATH = re.compile(r"^fixtures/[a-z0-9][a-z0-9_-]{0,63}\.md$")
_REPOSITORY_PATH = re.compile(r"^(src|tests|docs)(/[a-z0-9][a-z0-9_./-]{0,255})?$")


def validate_tool_call(name: str, arguments: Mapping[str, Any]) -> dict[str, str]:
    """Return a normalized test-only call or raise before any tool execution."""
    contract = CONTRACTS.get(name)
    if contract is None:
        raise McpPolicyError("tool is not allowlisted")
    if not isinstance(arguments, Mapping):
        raise McpPolicyError("arguments must be an object")
    keys = set(arguments)
    if contract.required - keys:
        raise McpPolicyError("required argument is missing")
    if keys - contract.allowed:
        raise McpPolicyError("unknown argument is forbidden")
    if not all(isinstance(value, str) for value in arguments.values()):
        raise McpPolicyError("arguments must be strings")

    normalized = {key: value.strip() for key, value in arguments.items()}
    if name == "test.docs.lookup" and not 1 <= len(normalized["query"]) <= 500:
        raise McpPolicyError("query length is outside policy")
    if name == "test.fixture.read" and not _FIXTURE_PATH.fullmatch(normalized["path"]):
        raise McpPolicyError("fixture path is outside allowlist")
    if name == "test.git.diff":
        if normalized["base"] != "HEAD" or not _REPOSITORY_PATH.fullmatch(normalized["path"]):
            raise McpPolicyError("git diff request is outside allowlist")
    return normalized


def mark_untrusted_result(content: str) -> dict[str, object]:
    """Preserve external text as data, explicitly preventing instruction trust."""
    return {"content": content, "trusted": False, "origin": "test-mcp"}
