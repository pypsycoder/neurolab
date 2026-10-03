"""Offline OpenAI protocol fixture, only reachable on an internal Docker network.

Not a model or agent: replay view -> replace -> finish on a synthetic probe file.
Never stores request bodies, prompts, model output or credentials.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os


def tool_reply(tools, step):
    functions = {item["function"]["name"]: item["function"] for item in tools if item.get("type") == "function"}
    editor = next((name for name in functions if name in {"file_editor", "str_replace_editor"}), None)
    if editor is None:
        raise ValueError("expected official file editor tool")
    if step == 0:
        action = {"command": "view", "path": "/workspace/experiment/probe.txt"}
    elif step == 1:
        action = {"command": "str_replace", "path": "/workspace/experiment/probe.txt", "old_str": "before", "new_str": "after"}
    else:
        return "finish", {"message": "Offline synthetic probe complete."}
    if os.environ.get("TOOL_PROBE_OMIT_RISK") != "1":
        action["security_risk"] = "LOW"
    return editor, action


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        payload = b'{"status":"ok"}'
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(payload)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 500000 or self.server.calls >= 6:
            self.send_error(400); return
        try:
            request = json.loads(self.rfile.read(length))
            name, arguments = tool_reply(request.get("tools", []), self.server.calls)
        except (ValueError, KeyError, TypeError):
            self.send_error(400); return
        self.server.calls += 1
        call = {"id": f"probe-{self.server.calls}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
        common = {"id": f"offline-probe-{self.server.calls}", "created": 1, "model": request.get("model", "offline-probe")}
        if request.get("stream"):
            self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
            chunks = [dict(common, object="chat.completion.chunk", choices=[{"index": 0, "delta": {"role": "assistant", "tool_calls": [dict(call, index=0)]}, "finish_reason": None}]),
                      dict(common, object="chat.completion.chunk", choices=[{"index": 0, "delta": {}, "finish_reason": "tool_calls"}])]
            for item in chunks:
                self.wfile.write(("data: " + json.dumps(item) + "\n\n").encode())
            self.wfile.write(b"data: [DONE]\n\n"); self.wfile.flush()
        else:
            payload = dict(common, object="chat.completion", choices=[{"index": 0, "message": {"role": "assistant", "content": None, "tool_calls": [call]}, "finish_reason": "tool_calls"}], usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(payload).encode())


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 8090), Handler)
    server.calls = 0
    server.serve_forever()
