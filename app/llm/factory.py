"""Factory: create the right LLM client from config."""

from app.llm.base import LLMClient

# provider → (module path, class name)
_REGISTRY = {
    "anthropic": ("app.llm.anthropic_client", "AnthropicClient"),
    "openai": ("app.llm.openai_client", "OpenAIClient"),
    "gemini": ("app.llm.gemini_client", "GeminiClient"),
    "mock": ("app.llm.mock_client", "MockClient"),
}


def create_client(provider: str, api_key: str, model: str) -> LLMClient:
    """Instantiate an LLM client by provider name.

    Args:
        provider: One of "anthropic", "openai", "gemini".
        api_key: API key for the provider.
        model: Model ID string.

    Raises:
        ValueError: If the provider is not supported.
        ImportError: If the provider's SDK is not installed.
    """
    if provider not in _REGISTRY:
        supported = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown provider '{provider}'. Supported: {supported}")

    module_path, class_name = _REGISTRY[provider]

    import importlib
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(api_key=api_key, model=model)
