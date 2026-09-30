import httpx
import time
import json

def test():
    t0 = time.time()
    prompt = """Analyze this goal: 'Organize a 30-minute sync meeting with Alice and Bob next Tuesday at 2 PM to review quarterly budget and email them the invite.'
Return strictly JSON with keys: objective, constraints, participants, deadline, required_capabilities, missing_information, clarification_needed.
Do NOT output any <think> tags. Start directly with {."""

    payload = {
        "model": "qwen3:4b",
        "messages": [
            {"role": "system", "content": "You are a work agent. Output only raw JSON. Never use <think> tags."},
            {"role": "user", "content": prompt}
        ],
        "format": "json",
        "stream": False,
        "options": {
            "num_ctx": 2048,
            "num_predict": 400,
            "temperature": 0.1
        }
    }
    print("Sending request...")
    res = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=120.0)
    elapsed = time.time() - t0
    print(f"Status: {res.status_code}, Elapsed: {elapsed:.2f}s")
    msg = res.json().get("message", {})
    print("Content:")
    print(msg.get("content"))

if __name__ == "__main__":
    test()
