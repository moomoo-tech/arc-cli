"""Anthropic (Claude) LLM client."""

import anthropic

from app.llm.base import LLMClient


class AnthropicClient(LLMClient):

    def __init__(self, api_key: str, model: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def chat(self, system: str, user: str, max_tokens: int = 4096) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text
