from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from typing import Optional, Dict, Any

from app.llm import get_llm_provider
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["Health"])

class BackendHealthResponse(BaseModel):
    status: str
    project: str
    version: str

class LLMHealthResponse(BaseModel):
    provider: str
    model: str
    reachable: bool
    available: bool
    status: str # "ready" | "unavailable" | "model_missing" | "error"
    error: Optional[str] = None
    details: Dict[str, Any] = {}

@router.get("", response_model=BackendHealthResponse)
async def check_backend_health():
    """Returns basic backend liveness status."""
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "version": "0.2.0"
    }

@router.get("/llm", response_model=LLMHealthResponse)
async def check_llm_health(response: Response):
    """
    Checks LLM reachability and model availability.
    Returns status: ready, unavailable, model_missing, not_configured, not_implemented, or error.
    """
    provider_name = settings.LLM_PROVIDER.lower().strip()
    try:
        provider = get_llm_provider()
        result = await provider.health_check()
        return result
    except Exception as e:
        error_code = getattr(e, "code", "error")
        error_status = "not_configured" if error_code == "not_configured" else (
            "not_implemented" if error_code == "not_implemented" else "error"
        )
        return {
            "provider": provider_name,
            "model": getattr(settings, "OLLAMA_MODEL", "unknown"),
            "reachable": False,
            "available": False,
            "status": error_status,
            "error": str(e),
            "details": getattr(e, "details", {})
        }

