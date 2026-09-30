import httpx
import time
import json
from app.schemas.goal import GoalUnderstanding

def test():
    t0 = time.time()
    system_prompt = (
        "You are Relay's Goal Understanding Agent. "
        "Analyze the user's goal and respond with ONLY a valid JSON object matching this exact structure:\n"
        "{\n"
        '  "objective": "Clear summary of user goal",\n'
        '  "constraints": ["boundary or rule 1"],\n'
        '  "participants": ["Alice", "Bob"],\n'
        '  "deadline": "next Tuesday at 2 PM",\n'
        '  "required_capabilities": ["calendar_create", "email_send"],\n'
        '  "missing_information": [],\n'
        '  "clarification_needed": false,\n'
        '  "clarification_questions": []\n'
        "}\n\n"
        "Allowed capability IDs: ['web_search', 'web_read', 'browser_navigate', 'calendar_read', 'calendar_create', 'calendar_delete', 'email_read', 'email_draft', 'email_send', 'message_send', 'issue_create', 'document_summarize', 'file_read', 'api_request', 'mcp_call'].\n"
        "Set clarification_needed = true ONLY if critical info is genuinely missing. Otherwise false.\n"
        "Output ONLY the JSON object. No extra text."
    )

    user_prompt = "Goal: Organize a 30-minute sync meeting with Alice and Bob next Tuesday at 2 PM to review quarterly budget, and email them the calendar invite."

    payload = {
        "model": "qwen3:4b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "format": "json",
        "stream": False,
        "options": {
            "num_ctx": 2048,
            "temperature": 0.1
        }
    }

    print("Sending Goal Understanding request with format='json'...")
    res = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=120.0)
    elapsed = time.time() - t0
    print(f"Completed in {elapsed:.2f}s, HTTP status: {res.status_code}")
    msg = res.json().get("message", {})
    content = msg.get("content", "")
    print("Content:", content)
    
    parsed = json.loads(content)
    validated = GoalUnderstanding.model_validate(parsed)
    print("\nSUCCESS! Validated Pydantic model:")
    print(json.dumps(validated.model_dump(), indent=2))

if __name__ == "__main__":
    test()
