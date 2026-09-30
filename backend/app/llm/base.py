from abc import ABC, abstractmethod
from typing import Type, TypeVar, Optional, Tuple, Any, Dict
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class LLMProvider(ABC):
    """Abstract base class for all LLM providers in Relay."""

    @abstractmethod
    async def generate_structured(
        self,
        schema: Type[T],
        prompt: str,
        system_prompt: Optional[str] = None,
        language: str = "en",
        max_retries: Optional[int] = None,
        temperature: float = 0.1,
        prompt_version: str = "1.0",
    ) -> Tuple[T, Dict[str, Any]]:
        """
        Generates schema-constrained output, validates against Pydantic schema,
        and applies bounded corrective retries on validation or JSON failure.
        
        Returns:
            Tuple of (validated_model_instance, call_metadata)
        """
        pass

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        language: str = "en",
        max_retries: Optional[int] = None,
        temperature: float = 0.7,
        prompt_version: str = "1.0",
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generates freeform text in the requested user language.
        
        Returns:
            Tuple of (text_response, call_metadata)
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Checks connectivity, model availability, and readiness.
        
        Returns:
            {
                "provider": str,
                "model": str,
                "reachable": bool,
                "available": bool,
                "status": "ready" | "unavailable" | "model_missing" | "error",
                "error": Optional[str],
                "details": dict
            }
        """
        pass
