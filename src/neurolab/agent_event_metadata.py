"""Allowlisted event counts only; no model text, commands, tool args or transcripts."""
import json

KINDS = {'action','observation','message','error','finish','ActionEvent','ObservationEvent','MessageEvent','AgentErrorEvent','AgentFinishEvent','ConversationStateUpdateEvent','SystemPromptEvent'}
TOOLS = {'terminal','file_editor','execute_bash','finish','think','str_replace_editor'}
MARKERS = {'RateLimitError','ReadTimeout','ConnectTimeout','PermissionError','AuthenticationError'}


def observe_line(line: bytes, counts: dict[str,int]) -> None:
    if len(line) > 65536:
        counts['oversized_event'] = min(1000,counts.get('oversized_event',0)+1)
        return
    for marker in MARKERS:
        if marker.encode() in line:
            counts[marker] = min(1000,counts.get(marker,0)+1)
    try:
        value = json.loads(line)
    except (ValueError,UnicodeError):
        return
    if not isinstance(value,dict):
        return
    counts['json_events'] = min(1000,counts.get('json_events',0)+1)
    kind = value.get('kind') or value.get('type')
    if isinstance(kind,str) and kind in KINDS:
        counts[kind] = min(1000,counts.get(kind,0)+1)
    tool = value.get('tool_name')
    if isinstance(tool,str) and tool in TOOLS:
        counts['tool:'+tool] = min(1000,counts.get('tool:'+tool,0)+1)

