from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.entities import Goal, User, Connection
from app.security.auth import get_optional_user
from app.schemas.goal import GoalUnderstandRequest, GoalUnderstandResponse
from app.services.goal_service import goal_service
from app.llm.errors import (
    LLMConnectionError,
    LLMModelMissingError,
    LLMTimeoutError,
    LLMSchemaValidationError,
    LLMInvalidJSONError,
    LLMError,
)

router = APIRouter(prefix="/goals", tags=["Goals"])

@router.post("/understand", response_model=GoalUnderstandResponse)
async def understand_goal(
    req: GoalUnderstandRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Analyzes natural language goal using the configured LLMProvider (Ollama qwen3:4b).
    Returns structured understanding, required capabilities, and clarification questions if needed.
    Persists Goal entity in database if caller is authenticated.
    """
    if not req.goal.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Goal text cannot be empty."
        )

    try:
        # If user is authenticated, sync any connected MCP capabilities so understanding prompt knows about them
        if current_user:
            c_stmt = select(Connection).where(Connection.user_id == current_user.id, Connection.status == "connected")
            c_res = await db.execute(c_stmt)
            for conn in c_res.scalars().all():
                if conn.app_id == "mcp" and conn.discovered_tools:
                    for item in conn.discovered_tools:
                        cap_id = item.get("capability_id")
                        if cap_id:
                            from app.tools.registry.capabilities import get_capability, register_capability, Capability
                            if not get_capability(cap_id):
                                register_capability(Capability(
                                    id=cap_id,
                                    label=item.get("capability_label", cap_id),
                                    category="mcp",
                                    default_risk=item.get("risk_profile", "medium"),
                                    description=item.get("description", f"MCP Tool for {cap_id}")
                                ))
                            if cap_id.endswith("_search"):
                                alias_cap_id = cap_id.replace("_search", "_read")
                                if not get_capability(alias_cap_id):
                                    register_capability(Capability(
                                        id=alias_cap_id,
                                        label=item.get("capability_label", cap_id).replace("Search", "Read"),
                                        category="mcp",
                                        default_risk=item.get("risk_profile", "medium"),
                                        description=f"Read {cap_id.replace('_search', '')} via MCP."
                                    ))
                            elif cap_id.endswith("_read"):
                                alias_cap_id = cap_id.replace("_read", "_search")
                                if not get_capability(alias_cap_id):
                                    register_capability(Capability(
                                        id=alias_cap_id,
                                        label=item.get("capability_label", cap_id).replace("Read", "Search"),
                                        category="mcp",
                                        default_risk=item.get("risk_profile", "medium"),
                                        description=f"Search {cap_id.replace('_read', '')} via MCP."
                                    ))

        response = await goal_service.understand_goal(req)

        # If user is authenticated, persist Goal row so it can be planned
        if current_user and response.goal_id:
            existing = await db.get(Goal, response.goal_id)
            if existing:
                existing.understanding = response.understanding.model_dump()
                existing.status = "understood"
            else:
                goal = Goal(
                    id=response.goal_id,
                    user_id=current_user.id,
                    text=req.goal,
                    language=req.language,
                    status="understood",
                    understanding=response.understanding.model_dump()
                )
                db.add(goal)
            await db.commit()

        return response
    except LLMConnectionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": e.message, "code": e.code, "details": e.details}
        )
    except LLMModelMissingError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": e.message, "code": e.code, "details": e.details}
        )
    except LLMTimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail={"message": e.message, "code": e.code, "details": e.details}
        )
    except (LLMSchemaValidationError, LLMInvalidJSONError) as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": e.message, "code": e.code, "details": e.details}
        )
    except LLMError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": e.message, "code": e.code, "details": e.details}
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": f"Unexpected error during goal understanding: {str(e)}", "code": "internal_error"}
        )
