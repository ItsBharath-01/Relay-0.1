import pytest
from app.core.config import settings
from app.llm import get_llm_provider
from app.llm.ollama import OllamaProvider
from app.llm.errors import ProviderNotConfiguredError, ProviderNotImplementedError, LLMProviderError

def test_ollama_provider_selected_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
    # Reset cached provider
    import app.llm as llm_mod
    llm_mod._cached_provider = None
    
    provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)

def test_gemini_without_api_key_raises_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    import app.llm as llm_mod
    llm_mod._cached_provider = None
    
    with pytest.raises(ProviderNotConfiguredError) as exc_info:
        get_llm_provider()
    assert exc_info.value.code == "not_configured"
    assert "GEMINI_API_KEY" in str(exc_info.value)

def test_anthropic_without_api_key_raises_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)
    import app.llm as llm_mod
    llm_mod._cached_provider = None
    
    with pytest.raises(ProviderNotConfiguredError) as exc_info:
        get_llm_provider()
    assert exc_info.value.code == "not_configured"

def test_unknown_provider_raises_provider_error(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "nonexistent_llm")
    import app.llm as llm_mod
    llm_mod._cached_provider = None
    
    with pytest.raises(LLMProviderError) as exc_info:
        get_llm_provider()
    assert "Unsupported LLM provider" in str(exc_info.value)
