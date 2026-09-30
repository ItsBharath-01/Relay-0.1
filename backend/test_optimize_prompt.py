import httpx
import time
import json

def test():
    # Test 1: format='json' (fast) vs format=huge_schema (slow grammar evaluator)
    prompt = """Analyze this goal:
"Organize a 30-minute sync meeting with Alice and Bob next Tuesday at 2 PM to review quarterly budget, and email them the calendar invite."

Allowed capabilities: ['web_search', 'web_read', 'calendar_create', 'calendar_read', 'calendar_delete', 'email_send', 'email_draft', 'message_send', 'issue_create', 'document_summarize']

Return JSON strictly with:
{
  "objective": "string",
  "constraints": ["string"],
  "participants": ["string"],
  "deadline": "string or null",
  "required_capabilities": ["calendar_create", "email_send"],
  "missing_information": [],
  "clarification_needed": false,
  "clarification_questions": []
}"""

    t0 = time.time()
    res = httpx.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "qwen3:4b",
            "messages": [
                {"role": "system", "content": "You are Relay. Output only valid JSON. Keep thinking under 10 words."},
                {"role": "user", "content": prompt}
            ],
            "format": "json",
            "stream": False,
            "options": {
                "num_ctx": 2048,
                "temperature": 0.1
            }
        },
        timeout=120
    )
    elapsed = time.time() - t0
    print(f"Elapsed with format='json': {elapsed:.2f}s")
    msg = res.json().get("message", {})
    print("Content:", msg.get("content"))
    print("Thinking len:", len(msg.get("thinking", "")))

if __name__ == "__main__":
    test()
