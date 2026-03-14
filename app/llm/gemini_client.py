"""Google Gemini LLM client."""

from google import genai
from google.genai import types

from app.llm.base import LLMClient


class GeminiClient(LLMClient):

    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def chat(self, system: str, user: str, max_tokens: int = 4096) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=65536,
            thinking_config=types.ThinkingConfig(thinking_budget=8192),
        )

        response = self._client.models.generate_content(
            model=self._model,
            contents=user,
            config=config,
        )

        # Extract text parts, skipping thinking parts
        parts = []
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if part.text and not getattr(part, "thought", False):
                    parts.append(part.text)
        return "\n".join(parts) if parts else ""
