import uuid
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.llm import get_llm_provider
from app.models.entities import Goal, Plan, Task, User, UserPreference, Connection
from app.schemas.plan import PlanSchema, PlanTaskSchema, PlanUpdateRequest
from app.agent.prompts.planning import build_planning_prompt, PLANNING_PROMPT_VERSION
from app.selection.engine import selection_engine
from app.risk.classifier import risk_classifier

class RawGeneratedTask(BaseModel):
    id: str
    order: int
    title: str
    capability_id: str
    depends_on: List[str] = Field(default_factory=list)
    action: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)

class RawGeneratedPlan(BaseModel):
    tasks: List[RawGeneratedTask]

class PlanningService:
    def __init__(self):
        self.provider = get_llm_provider()

    async def create_plan_for_goal(
        self,
        goal_id: str,
        user_id: str,
        db: AsyncSession
    ) -> PlanSchema:
        # Load goal
        stmt = select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
        res = await db.execute(stmt)
        goal = res.scalar_one_or_none()
        if not goal:
            raise ValueError("Goal not found or unauthorized.")

        # Load user preferences
        p_stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        p_res = await db.execute(p_stmt)
        preferences = p_res.scalar_one_or_none() or UserPreference(user_id=user_id)

        understanding = goal.understanding or {}
        objective = understanding.get("objective", goal.text)
        desired_outcome = understanding.get("desired_outcome")
        success_criteria = understanding.get("success_criteria", [])
        constraints = understanding.get("constraints", [])
        participants = understanding.get("participants", [])
        deadline = understanding.get("deadline")
        required_caps = understanding.get("required_capabilities", [])
        # Ensure user's connected MCP capabilities are loaded and registered
        c_stmt = select(Connection).where(Connection.user_id == user_id, Connection.status == "connected")
        c_res = await db.execute(c_stmt)
        user_conns = c_res.scalars().all()
        for conn in user_conns:
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

        # Build prompt
        sys_prompt, user_prompt = build_planning_prompt(
            goal=goal.text,
            objective=objective,
            constraints=constraints,
            participants=participants,
            deadline=deadline,
            required_capabilities=required_caps,
            language=goal.language or "en",
            desired_outcome=desired_outcome,
            success_criteria=success_criteria
        )

        # Generate plan via LLM
        raw_plan, meta = await self.provider.generate_structured(
            schema=RawGeneratedPlan,
            prompt=user_prompt,
            system_prompt=sys_prompt,
            language=goal.language or "en",
            temperature=0.1,
            prompt_version=PLANNING_PROMPT_VERSION,
        )

        # Create Plan entity in DB
        new_plan = Plan(
            goal_id=goal.id,
            version=1,
            is_active=True
        )
        db.add(new_plan)
        await db.flush()

        task_schemas: List[PlanTaskSchema] = []
        missing_capabilities: List[str] = []
        all_tools_available = True

        for idx, t in enumerate(raw_plan.tasks, start=1):
            cap_id = t.capability_id.strip()

            # Run real tool selection check
            decision = await selection_engine.evaluate_candidates(
                user_id=user_id,
                capability_id=cap_id,
                db=db,
                task_id=t.id
            )

            candidate_tool_ids = [c.tool_id for c in decision.candidate_checks]
            has_tool = bool(decision.selected_tool_id)

            if not has_tool:
                all_tools_available = False
                if cap_id not in missing_capabilities:
                    missing_capabilities.append(cap_id)

            # Assess real risk
            risk_assessment = risk_classifier.assess_action(
                capability_id=cap_id,
                action=t.action or cap_id,
                params=t.params,
                preferences=preferences
            )

            # Save task to DB — persist LLM-generated action and params so executor never invents them
            db_task = Task(
                id=str(uuid.uuid4()),
                plan_id=new_plan.id,
                order=idx,
                title=t.title,
                capability_id=cap_id,
                candidate_tool_ids=candidate_tool_ids,
                depends_on=t.depends_on,
                risk_level=risk_assessment.risk_level,
                requires_approval=risk_assessment.requires_approval,
                action=t.action or cap_id,
                params=t.params if t.params else {},
                description=t.title,
                status="pending",
                selected_tool_id=decision.selected_tool_id,
            )
            db.add(db_task)

            task_schemas.append(PlanTaskSchema(
                id=db_task.id,
                order=idx,
                title=t.title,
                capability_id=cap_id,
                candidate_tool_ids=candidate_tool_ids,
                depends_on=t.depends_on,
                risk_level=risk_assessment.risk_level,
                requires_approval=risk_assessment.requires_approval,
                status="pending",
                has_connected_tool=has_tool,
                selected_tool_id=decision.selected_tool_id,
                selected_tool_name=decision.selected_tool_name,
                action=t.action or cap_id,
                params=t.params
            ))

        goal.status = "planned"
        await db.commit()

        return PlanSchema(
            id=new_plan.id,
            goal_id=goal.id,
            version=new_plan.version,
            tasks=task_schemas,
            all_tools_available=all_tools_available,
            missing_capabilities=missing_capabilities
        )

    async def get_plan(self, plan_id: str, user_id: str, db: AsyncSession) -> PlanSchema:
        stmt = (
            select(Plan)
            .join(Goal, Plan.goal_id == Goal.id)
            .options(selectinload(Plan.tasks))
            .where(Plan.id == plan_id, Goal.user_id == user_id)
        )
        res = await db.execute(stmt)
        plan = res.scalar_one_or_none()
        if not plan:
            raise ValueError("Plan not found.")

        missing_caps = []
        task_schemas = []
        from app.tools.registry import get_tool
        for t in plan.tasks:
            has_tool = bool(t.selected_tool_id)
            tool_obj = get_tool(t.selected_tool_id) if t.selected_tool_id else None
            tool_name = tool_obj.name if tool_obj else t.selected_tool_id
            if not has_tool:
                missing_caps.append(t.capability_id)
            task_schemas.append(PlanTaskSchema(
                id=t.id,
                order=t.order,
                title=t.title,
                capability_id=t.capability_id,
                candidate_tool_ids=t.candidate_tool_ids or [],
                depends_on=t.depends_on or [],
                risk_level=t.risk_level,
                requires_approval=t.requires_approval,
                status=t.status,
                has_connected_tool=has_tool,
                selected_tool_id=t.selected_tool_id,
                selected_tool_name=tool_name,
            ))

        return PlanSchema(
            id=plan.id,
            goal_id=plan.goal_id,
            version=plan.version,
            tasks=task_schemas,
            all_tools_available=len(missing_caps) == 0,
            missing_capabilities=missing_caps
        )

planning_service = PlanningService()
