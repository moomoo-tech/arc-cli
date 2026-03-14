"""Abstract LLM client interface."""

from abc import ABC, abstractmethod


class LLMClient(ABC):
    """Common interface for all LLM providers."""

    @abstractmethod
    def chat(self, system: str, user: str, max_tokens: int = 4096) -> str:
        """Send a single-turn chat and return the response text.

        Args:
            system: System prompt.
            user: User message.
            max_tokens: Maximum tokens in the response.

        Returns:
            The model's text response.
        """
