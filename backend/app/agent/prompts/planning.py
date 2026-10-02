from typing import List, Dict, Any, Optional
from app.tools.registry.capabilities import get_all_capabilities

PLANNING_PROMPT_VERSION = "1.0.0"

PLANNING_SYSTEM_INSTRUCTIONS = """You are Relay's Planning Agent (v{version}).
Decompose the validated goal into an ordered, executable task graph.

OUTPUT FORMAT:
Respond with ONLY a valid JSON object matching this structure:
{{
  "tasks": [
    {{
      "id": "task_1",
      "order": 1,
      "title": "Clear action-oriented task title",
      "capability_id": "calendar_create",
      "depends_on": [],
      "action": "calendar_create",
      "params": {{
        "summary": "Project Sync",
        "start_time": "2026-10-06T14:00:00"
      }}
    }},
    {{
      "id": "task_2",
      "order": 2,
      "title": "Email confirmation to team",
      "capability_id": "email_send",
      "depends_on": ["task_1"],
      "action": "email_send",
      "params": {{
        "to": "team@example.com",
        "subject": "Project Sync Invitation"
      }}
    }}
  ]
}}

ALLOWED CAPABILITY IDS:
{capability_list}

RULES:
1. Every task must use a valid capability_id from the allowed list.
2. Link dependencies correctly in 'depends_on'. If task 2 needs output from task 1, add task 1's ID.
3. Titles must be in language: '{language}'. Capability IDs and actions stay in English.
4. Keep the plan minimal, direct, and executable (typically 2 to 5 tasks).
5. HONEST CAPABILITY MATCHING: Never substitute 'web_search' or 'web_read' as a substitute for real application operations (e.g., playing audio/video, creating documents, booking, sending payments, controlling native apps). If the action requires playing media or controlling an app, and no dedicated capability exists in ALLOWED CAPABILITY IDS, declare the true capability needed (e.g. 'media_play') rather than faking it with web_search.
6. Do NOT produce any <think> reasoning thoughts. Output ONLY the valid JSON object directly starting with {{ and ending with }}.
""".strip()

def build_planning_prompt(
    goal: str,
    objective: str,
    constraints: List[str],
    participants: List[str],
    deadline: Optional[str],
    required_capabilities: List[str],
    language: str = "en",
    desired_outcome: Optional[str] = None,
    success_criteria: Optional[List[str]] = None,
) -> tuple[str, str]:
    caps = get_all_capabilities()
    cap_lines = ", ".join([f"'{c.id}'" for c in caps])

    system_prompt = PLANNING_SYSTEM_INSTRUCTIONS.format(
        version=PLANNING_PROMPT_VERSION,
        capability_list=cap_lines,
        language=language
    )

    criteria_str = "\n".join([f"- {sc}" for sc in (success_criteria or [])]) or "None"

    user_prompt = (
        f"Goal: {goal}\n"
        f"Objective: {objective}\n"
        f"Desired Real-World Outcome: {desired_outcome or objective}\n"
        f"Success Criteria To Achieve:\n{criteria_str}\n"
        f"Constraints: {', '.join(constraints) if constraints else 'None'}\n"
        f"Participants: {', '.join(participants) if participants else 'None'}\n"
        f"Deadline: {deadline or 'None'}\n"
        f"Target Capabilities: {', '.join(required_capabilities)}\n"
        f"Language: {language}\n\n"
        "Generate the task graph plan now in valid JSON."
    )

    return system_prompt, user_prompt
