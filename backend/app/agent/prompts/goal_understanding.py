from typing import Optional, List, Dict
from app.tools.registry.capabilities import get_all_capabilities

PROMPT_VERSION = "1.0.0"

SYSTEM_INSTRUCTIONS = """You are Relay's Goal Understanding Agent (v{version}).
Analyze the user's natural language goal and respond with ONLY a valid JSON object matching this structure:
{{
  "objective": "Clear summary of what the user wants to accomplish",
  "constraints": ["constraint 1", "constraint 2"],
  "participants": ["Alice", "Bob"],
  "deadline": "deadline if specified, or null",
  "required_capabilities": ["calendar_create", "email_send"],
  "missing_information": [],
  "clarification_needed": false,
  "clarification_questions": []
}}

ALLOWED CAPABILITY IDS (strictly select only from this list):
{capability_list}

RULES:
1. Only set clarification_needed = true if CRITICAL information is truly missing that prevents execution.
2. User-facing text must be in language: '{language}'. Capability IDs must stay in English.
3. Do NOT produce any <think> reasoning thoughts. Output ONLY the valid JSON object directly starting with {{ and ending with }}.
""".strip()

def build_goal_understanding_prompt(
    goal: str,
    language: str = "en",
    context: Optional[str] = None,
    attachments: Optional[List[str]] = None,
    clarification_answers: Optional[Dict[str, str]] = None,
) -> tuple[str, str]:
    """
    Constructs the compact versioned system prompt and user intent prompt.
    Returns: (system_prompt, user_prompt)
    """
    caps = get_all_capabilities()
    cap_lines = ", ".join([f"'{c.id}'" for c in caps])

    system_prompt = SYSTEM_INSTRUCTIONS.format(
        version=PROMPT_VERSION,
        capability_list=cap_lines,
        language=language
    )

    user_sections = [
        f"Goal: {goal}",
        f"Language requested for explanations: {language}"
    ]

    if clarification_answers:
        user_sections.append("\nPRIOR CLARIFICATION ANSWERS:")
        for q, a in clarification_answers.items():
            user_sections.append(f"- Q: {q} => Answer: {a}")

    if context:
        user_sections.append(f"\nContext: {context}")
    if attachments:
        user_sections.append(f"\nAttachments: {', '.join(attachments)}")

    user_sections.append("\nOutput ONLY the JSON object.")
    user_prompt = "\n".join(user_sections)
    return system_prompt, user_prompt
