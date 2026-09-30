import httpx
import time
import json
from app.schemas.goal import GoalUnderstanding

def test():
    t0 = time.time()
    schema = GoalUnderstanding.model_json_schema()
    payload = {
        "model": "qwen3:4b",
        "messages": [
            {
                "role": "system",
                "content": "You are Relay, an autonomous work agent. Analyze the goal and return JSON adhering to the schema."
            },
            {
                "role": "user",
                "content": "Goal: Organize a 30-minute sync meeting with Alice and Bob next Tuesday at 2 PM to review quarterly budget, and email them the calendar invite."
            }
        ],
        "format": schema,
        "stream": False,
        "options": {
            "num_ctx": 4096,
            "temperature": 0.1
        }
    }
    print("Testing format: schema with qwen3:4b...")
    res = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=240.0)
    elapsed = time.time() - t0
    print(f"Elapsed: {elapsed:.2f}s, HTTP status: {res.status_code}")
    msg = res.json().get("message", {})
    content = msg.get("content", "")
    print("Content:")
    print(content)
    parsed = json.loads(content)
    validated = GoalUnderstanding.model_validate(parsed)
    print("VALIDATION SUCCESS:")
    print(validated)

if __name__ == "__main__":
    test()
