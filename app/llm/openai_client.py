"""OpenAI (GPT) LLM client."""

from openai import OpenAI

from app.llm.base import LLMClient


class OpenAIClient(LLMClient):

    def __init__(self, api_key: str, model: str):
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def chat(self, system: str, user: str, max_tokens: int = 500_000) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content

    def chat_multi(self, system: str, messages: list[dict[str, str]], max_tokens: int = 500_000) -> str:
        all_messages = [{"role": "system", "content": system}, *messages]
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=all_messages,
        )
        return response.choices[0].message.content
