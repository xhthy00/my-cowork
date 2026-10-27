"""JSON-safe tool content carried unchanged through the host/harness boundary."""
import json

RESULT_TAG = "__cowork_tool_result__"


def mcp_result(result):
    blocks = []
    rich = bool(result.get("isError"))
    for part in result.get("content") or []:
        kind = part.get("type")
        if kind == "text":
            blocks.append({"type": "text", "text": str(part.get("text", ""))})
        elif kind in {"image", "audio"}:
            rich = True
            blocks.append({"type": kind, "base64": part["data"], "mime_type": part["mimeType"]})
        elif kind == "resource" and "text" in part.get("resource", {}):
            rich = True
            resource = part["resource"]
            blocks.append({"type": "text", "text": resource.get("uri", "") + "\n" + resource["text"]})
        elif kind == "resource" and str(part.get("resource", {}).get("mimeType", "")).startswith("image/"):
            rich = True
            resource = part["resource"]
            blocks.append({"type": "image", "base64": resource["blob"], "mime_type": resource["mimeType"]})
        else:
            rich = True
            blocks.append({"type": "text", "text": json.dumps(part, ensure_ascii=False)})
    if "structuredContent" in result:
        rich = True
        blocks.append({"type": "text", "text": json.dumps(result["structuredContent"], ensure_ascii=False)})
    if not rich:
        return "\n".join(block["text"] for block in blocks) if blocks else json.dumps(result, ensure_ascii=False)
    return {RESULT_TAG: 1, "content": blocks, "is_error": bool(result.get("isError"))}
