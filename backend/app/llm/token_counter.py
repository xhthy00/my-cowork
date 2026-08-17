"""Token counting via tiktoken for budget tracking (with offline fallback)."""

from typing import Union

from langchain_core.messages import BaseMessage

_MsgInput = Union[str, list[str], list[BaseMessage]]

_enc = None
_enc_failed = False


def _get_enc():
    global _enc, _enc_failed
    if _enc is not None or _enc_failed:
        return _enc
    try:
        import tiktoken

        _enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _enc_failed = True
        _enc = None
    return _enc


def _texts(content: _MsgInput) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, BaseMessage):
                text = item.content
                if isinstance(text, str):
                    texts.append(text)
                elif isinstance(text, list):
                    for part in text:
                        if isinstance(part, dict) and "text" in part:
                            texts.append(part["text"])
                        elif isinstance(part, str):
                            texts.append(part)
            elif isinstance(item, str):
                texts.append(item)
        return texts
    return []


def count_tokens(content: _MsgInput) -> int:
    texts = _texts(content)
    joined = " ".join(texts)
    enc = _get_enc()
    if enc is not None:
        return len(enc.encode(joined))
    # Offline fallback (~4 chars / token)
    return max(1, len(joined) // 4) if joined else 0
