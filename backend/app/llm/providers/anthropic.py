"""Anthropic provider via langchain_anthropic."""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel


def create_anthropic(model: str, api_key: str) -> BaseChatModel:
    return ChatAnthropic(model=model, api_key=api_key)
