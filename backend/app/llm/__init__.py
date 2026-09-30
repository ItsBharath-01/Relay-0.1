from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.ollama import OllamaProvider
from app.llm.errors import (
    LLMError,
    LLMConnectionError,
    LLMModelMissingError,
    LLMTimeoutError,
    LLMInvalidJSONError,
    LLMSchemaValidationError,
    LLMRateLimitError,
    LLMProviderError,
    ProviderNotConfiguredError,
    ProviderNotImplementedError,
)

_cached_provider: LLMProvider = None

def get_llm_provider() -> LLMProvider:
    """
    Returns the configured LLM provider.
    Strictly adheres to settings.LLM_PROVIDER and never silently falls back.
    """
    global _cached_provider
    if _cached_provider is not None:
        return _cached_provider

    provider_type = settings.LLM_PROVIDER.lower().strip()
    if provider_type == "ollama":
        _cached_provider = OllamaProvider(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            num_ctx=settings.OLLAMA_NUM_CTX,
            timeout=settings.OLLAMA_TIMEOUT,
            max_retries=settings.OLLAMA_MAX_RETRIES,
        )
    elif provider_type == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ProviderNotConfiguredError("gemini", missing_key="GEMINI_API_KEY")
        raise ProviderNotImplementedError("gemini", message="Gemini provider is coming soon. Use local Ollama.")
    elif provider_type == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise ProviderNotConfiguredError("anthropic", missing_key="ANTHROPIC_API_KEY")
        raise ProviderNotImplementedError("anthropic", message="Anthropic provider is coming soon. Use local Ollama.")
    elif provider_type == "openai":
        if not settings.OPENAI_API_KEY:
            raise ProviderNotConfiguredError("openai", missing_key="OPENAI_API_KEY")
        raise ProviderNotImplementedError("openai", message="OpenAI provider is coming soon. Use local Ollama.")
    else:
        raise LLMProviderError(f"Unsupported LLM provider '{settings.LLM_PROVIDER}'. Supported options: ollama, gemini, anthropic, openai.")

    return _cached_provider

