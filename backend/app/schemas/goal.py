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
    deadline: Optional[str] = Field(default=None, description="Target completion date/time or deadline if mentioned, or null.")
    required_capabilities: List[CapabilityId] = Field(
        default_factory=list,
        description="List of capability IDs needed to achieve the goal. Must strictly be from the allowed registry enum."
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
            # Normalize required_capabilities aliases if present
            raw_caps = data.get("required_capabilities", [])
            normalized = []
            valid_set = set(get_valid_capability_ids())
            for cap in raw_caps:
                c_str = str(cap).strip().lower()
                if c_str in valid_set:
                    normalized.append(c_str)
                elif c_str in CAPABILITY_ALIASES:
                    normalized.append(CAPABILITY_ALIASES[c_str])
            data["required_capabilities"] = normalized
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
