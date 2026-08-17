#!/usr/bin/env python3
"""Minimal MCP stdio echo server for tests.

Speaks newline-delimited JSON-RPC. Exposes one tool: ``echo``.
"""

from __future__ import annotations

import json
import sys


def respond(msg_id, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        msg_id = msg.get("id")
        if method == "initialize":
            respond(
                msg_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "echo", "version": "0.1.0"},
                },
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            respond(
                msg_id,
                {
                    "tools": [
                        {
                            "name": "echo",
                            "description": "Echo back the text argument",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string", "description": "text to echo"}
                                },
                                "required": ["text"],
                            },
                        }
                    ]
                },
            )
        elif method == "tools/call":
            params = msg.get("params") or {}
            args = params.get("arguments") or {}
            text = str(args.get("text", ""))
            respond(
                msg_id,
                {"content": [{"type": "text", "text": text}], "isError": False},
            )
        elif msg_id is not None:
            respond(msg_id, {})


if __name__ == "__main__":
    main()
