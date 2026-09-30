import httpx
import time

def test_prompt(name, system, user):
    t0 = time.time()
    payload = {
        "model": "qwen3:4b",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "format": "json",
        "stream": False,
        "options": {
            "num_ctx": 2048,
            "temperature": 0.0
        }
    }
    res = httpx.post("http://localhost:11434/api/chat", json=payload, timeout=90.0)
    elapsed = time.time() - t0
    msg = res.json().get("message", {})
    thinking = msg.get("thinking", "")
    content = msg.get("content", "")
    print(f"[{name}] Elapsed: {elapsed:.2f}s | Think len: {len(thinking)} | Content: {content[:100]}")

if __name__ == "__main__":
    test_prompt("1. Direct instruction", "Respond with pure JSON only. Do not reason or think.", "Return JSON: {\"status\": \"ok\"}")
    test_prompt("2. Think disable instruction", "Thinking is disabled. Immediately output raw JSON: {\"status\": \"ready\"}.", "Generate JSON now.")
