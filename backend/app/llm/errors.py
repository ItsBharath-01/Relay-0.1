class LLMError(Exception):
    """Base class for all LLM errors."""
    def __init__(self, message: str, code: str = "llm_error", details: dict = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}

class LLMConnectionError(LLMError):
    """Raised when the LLM service cannot be reached."""
    def __init__(self, message: str = "Cannot connect to LLM service", details: dict = None):
        super().__init__(message, code="llm_unavailable", details=details)

class LLMModelMissingError(LLMError):
    """Raised when the configured model is not pulled or missing."""
    def __init__(self, model_name: str, message: str = None, details: dict = None):
        msg = message or f"Configured model '{model_name}' is not installed in Ollama. Run: ollama pull {model_name}"
        super().__init__(msg, code="model_missing", details=details or {"model": model_name})

class LLMTimeoutError(LLMError):
    """Raised when the LLM generation times out."""
    def __init__(self, message: str = "LLM request timed out", details: dict = None):
        super().__init__(message, code="llm_timeout", details=details)

class LLMInvalidJSONError(LLMError):
    """Raised when the LLM output is not valid JSON."""
    def __init__(self, raw_output: str, message: str = "LLM response is not valid JSON", details: dict = None):
        d = details or {}
        d["raw_snippet"] = raw_output[:300] if raw_output else ""
        super().__init__(message, code="invalid_json", details=d)

class LLMSchemaValidationError(LLMError):
    """Raised when the LLM JSON output fails Pydantic schema validation."""
    def __init__(self, schema_name: str, errors: list, raw_json: dict = None, details: dict = None):
        d = details or {}
        d["schema"] = schema_name
        d["validation_errors"] = errors
        d["raw_json"] = raw_json
        super().__init__(f"LLM output failed validation for schema {schema_name}", code="schema_validation_failed", details=d)

class LLMRateLimitError(LLMError):
    """Raised when rate limit or resource capacity is exceeded."""
    def __init__(self, message: str = "LLM rate limit or resource capacity exceeded", details: dict = None):
        super().__init__(message, code="rate_limit", details=details)

class LLMProviderError(LLMError):
    """General unexpected provider error."""
    def __init__(self, message: str, details: dict = None):
        super().__init__(message, code="provider_error", details=details)

class ProviderNotConfiguredError(LLMError):
    """Raised when a requested LLM provider is missing required configuration (e.g. API keys)."""
    def __init__(self, provider: str, missing_key: str = None, message: str = None):
        msg = message or f"LLM provider '{provider}' is not configured (missing {missing_key or 'credentials'})."
        super().__init__(msg, code="not_configured", details={"provider": provider, "missing_key": missing_key})

class ProviderNotImplementedError(LLMError):
    """Raised when a requested LLM provider is recognized but not implemented in this build."""
    def __init__(self, provider: str, message: str = None):
        msg = message or f"LLM provider '{provider}' is not implemented in this environment."
        super().__init__(msg, code="not_implemented", details={"provider": provider})

