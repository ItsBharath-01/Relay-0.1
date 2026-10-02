from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from app.tools.registry.capabilities import get_valid_capability_ids

CapabilityId = Literal[
    "web_search",
    "web_read",
    "browser_navigate",
    "calendar_read",
    "calendar_create",
    "calendar_delete",
    "email_read",
    "email_draft",
    "email_send",
    "message_send",
    "issue_create",
    "document_summarize",
    "file_read",
    "api_request",
    "mcp_call",
]

# Shorthand aliases normalizer for LLMs
CAPABILITY_ALIASES: Dict[str, str] = {
    "calendar": "calendar_create",
    "schedule": "calendar_create",
    "meeting": "calendar_create",
    "email": "email_send",
    "mail": "email_send",
    "gmail": "email_send",
    "slack": "message_send",
    "chat": "message_send",
    "search": "web_search",
    "web": "web_search",
    "browse": "browser_navigate",
    "browser": "browser_navigate",
    "summarize": "document_summarize",
    "summary": "document_summarize",
    "github": "issue_create",
    "issue": "issue_create",
}

class ClarificationOption(BaseModel):
    id: str
    label: str

class ClarificationQuestion(BaseModel):
    id: str
    question: str
    options: List[ClarificationOption] = Field(default_factory=list)
    allow_custom: bool = True

class GoalUnderstanding(BaseModel):
    objective: str = Field(description="Clear, concise summary of what the user wants to accomplish.")
    constraints: List[str] = Field(default_factory=list, description="Any boundaries, limits, preferences or rules.")
    participants: List[str] = Field(default_factory=list, description="People, teams, or services mentioned.")
    desired_outcome: Optional[str] = Field(default=None, description="The real-world end outcome the user expects upon completion.")
    success_criteria: List[str] = Field(
        default_factory=list,
        description="Explicit, checkable conditions describing what proves the user's objective was genuinely achieved."
    )
    required_capabilities: List[str] = Field(
        default_factory=list,
        description="List of capability IDs needed to achieve the goal. Must strictly match registered capability IDs."
    )
    missing_information: List[str] = Field(
        default_factory=list,
        description="Critical missing details that prevent safe execution without clarification."
    )
    clarification_needed: bool = Field(
        default=False,
        description="True ONLY if critical information is genuinely missing to form an executable plan."
    )
    clarification_questions: List[ClarificationQuestion] = Field(
        default_factory=list,
        description="Specific clarification questions to present to the user if clarification_needed is true."
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 1. Sanitize lists vs single strings for constraints, participants, success_criteria, missing_information
            for list_field in ("constraints", "participants", "success_criteria", "missing_information"):
                val = data.get(list_field)
                if isinstance(val, str):
                    data[list_field] = [val] if val.strip() else []
                elif val is None:
                    data[list_field] = []
                elif not isinstance(val, list):
                    data[list_field] = [str(val)]

            # 2. Sanitize boolean for clarification_needed
            cn = data.get("clarification_needed")
            if isinstance(cn, str):
                data["clarification_needed"] = cn.strip().lower() in ("true", "1", "yes")
            elif cn is None:
                data["clarification_needed"] = False

            # 3. Sanitize deadline
            if "deadline" in data and data["deadline"] is not None:
                if not isinstance(data["deadline"], str) or data["deadline"].strip().lower() in ("null", "none", ""):
                    data["deadline"] = None

            # 4. Normalize required_capabilities aliases and dynamic capabilities
            raw_caps = data.get("required_capabilities", [])
            if isinstance(raw_caps, str):
                raw_caps = [raw_caps]
            elif raw_caps is None:
                raw_caps = []

            normalized = []
            valid_set = set(get_valid_capability_ids())
            for cap in raw_caps:
                c_str = str(cap).strip().lower()
                # Direct match with registered capabilities
                if c_str in valid_set:
                    normalized.append(c_str)
                    continue

                # Check known alias map
                if c_str in CAPABILITY_ALIASES:
                    alias_target = CAPABILITY_ALIASES[c_str]
                    if alias_target in valid_set or not valid_set:
                        normalized.append(alias_target)
                        continue

                # Try verb-noun to noun-verb inversion (e.g. create_note -> note_create)
                if "_" in c_str:
                    parts = c_str.split("_", 1)
                    inverted = f"{parts[1]}_{parts[0]}"
                    if inverted in valid_set:
                        normalized.append(inverted)
                        continue

                # Try prefix/substring match against registered dynamic capabilities
                matched = False
                for v in valid_set:
                    if c_str == v.replace("_", "") or c_str in v:
                        normalized.append(v)
                        matched = True
                        break
                if not matched:
                    # If capability is explicitly declared or unrecognized, retain if valid identifier
                    if c_str.isidentifier():
                        normalized.append(c_str)

            data["required_capabilities"] = list(dict.fromkeys(normalized))

            # 5. Normalize clarification_questions: LLMs often output list of strings instead of ClarificationQuestion dicts
            raw_questions = data.get("clarification_questions", [])
            if isinstance(raw_questions, str):
                raw_questions = [raw_questions]
            elif raw_questions is None:
                raw_questions = []

            normalized_q = []
            for i, q in enumerate(raw_questions, start=1):
                if isinstance(q, str):
                    if q.strip():
                        normalized_q.append({
                            "id": f"q_{i}",
                            "question": q.strip(),
                            "options": [],
                            "allow_custom": True
                        })
                elif isinstance(q, dict):
                    if "id" not in q:
                        q["id"] = f"q_{i}"
                    if "question" not in q:
                        q["question"] = q.get("text", "")
                    normalized_q.append(q)
            data["clarification_questions"] = normalized_q
        return data

class GoalUnderstandRequest(BaseModel):
    goal_id: Optional[str] = None
    goal: str
    language: str = "en"
    context: Optional[str] = None
    attachments: Optional[List[str]] = None
    clarification_answers: Optional[Dict[str, str]] = None

class GoalUnderstandResponse(BaseModel):
    goal_id: Optional[str] = None
    original_goal: str
    language: str
    understanding: GoalUnderstanding
    provider_meta: Dict[str, Any] = Field(default_factory=dict)
