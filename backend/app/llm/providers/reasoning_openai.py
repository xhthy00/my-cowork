"""Preserve compatible vendors' reasoning fields across a tool-call round trip.

LangChain's chat-completions converter currently discards these extension fields.
Keep this shim local; Responses API payloads are handled by LangChain unchanged.
"""
import hashlib

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage

_FIELDS = ("reasoning_content", "reasoning_details")


class ReasoningChatOpenAI(ChatOpenAI):
    @property
    def _reasoning_origin(self) -> int:
        value = f"{self.openai_api_base}:{self.model_name}".encode()
        return int.from_bytes(hashlib.sha256(value).digest()[:6], "big")

    def _copy_reasoning(self, target, source):
        for key in _FIELDS:
            if source.get(key) is not None:
                target.additional_kwargs[key] = source[key]
                target.response_metadata["reasoning_origin"] = self._reasoning_origin
        extras = [{"index": call.get("index", index), "extra_content": call["extra_content"]}
                  for index, call in enumerate(source.get("tool_calls") or []) if call.get("extra_content")]
        if extras:
            target.additional_kwargs["provider_tool_extras"] = extras
            target.response_metadata["reasoning_origin"] = self._reasoning_origin

    def _convert_chunk_to_generation_chunk(self, chunk, default_chunk_class, base_generation_info):
        result = super()._convert_chunk_to_generation_chunk(chunk, default_chunk_class, base_generation_info)
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices", [])
        if result and choices:
            self._copy_reasoning(result.message, choices[0].get("delta") or {})
        return result

    def _create_chat_result(self, response, generation_info=None):
        result = super()._create_chat_result(response, generation_info)
        raw = response if isinstance(response, dict) else response.model_dump()
        for generation, choice in zip(result.generations, raw.get("choices", [])):
            self._copy_reasoning(generation.message, choice.get("message", {}))
        return result

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(messages, stop=stop, **kwargs)
        for source, target in zip(messages, payload.get("messages", [])):
            if isinstance(source, AIMessage) and source.response_metadata.get("reasoning_origin") == self._reasoning_origin:
                for key in _FIELDS:
                    if key in source.additional_kwargs:
                        target[key] = source.additional_kwargs[key]
                calls = target.get("tool_calls") or []
                for extra in source.additional_kwargs.get("provider_tool_extras", []):
                    index = extra.get("index", -1)
                    if isinstance(index, int) and 0 <= index < len(calls):
                        calls[index]["extra_content"] = extra["extra_content"]
        return payload
