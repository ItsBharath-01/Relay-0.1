import uuid
from typing import Dict, Any, Optional
from app.llm import get_llm_provider
from app.schemas.goal import GoalUnderstandRequest, GoalUnderstandResponse, GoalUnderstanding
from app.agent.prompts.goal_understanding import build_goal_understanding_prompt, PROMPT_VERSION

class GoalService:
    def __init__(self):
        self.provider = get_llm_provider()

    async def understand_goal(self, req: GoalUnderstandRequest) -> GoalUnderstandResponse:
        """
        Executes goal understanding with the configured LLMProvider.
        Strictly returns validated GoalUnderstanding model or raises typed LLM errors.
        """
        sys_prompt, user_prompt = build_goal_understanding_prompt(
            goal=req.goal,
            language=req.language,
            context=req.context,
            attachments=req.attachments,
            clarification_answers=req.clarification_answers,
        )

        understanding, meta = await self.provider.generate_structured(
            schema=GoalUnderstanding,
            prompt=user_prompt,
            system_prompt=sys_prompt,
            language=req.language,
            temperature=0.1,
            prompt_version=PROMPT_VERSION,
        )

        goal_id = req.goal_id or f"goal_{uuid.uuid4().hex[:12]}"

        return GoalUnderstandResponse(
            goal_id=goal_id,
            original_goal=req.goal,
            language=req.language,
            understanding=understanding,
            provider_meta=meta
        )

goal_service = GoalService()
