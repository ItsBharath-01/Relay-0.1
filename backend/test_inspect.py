import httpx
import json

r = httpx.post(
    "http://localhost:11434/api/chat",
    json={
        "model": "qwen3:4b",
        "messages": [{"role": "user", "content": "Return JSON: {\"status\": \"ok\"}"}],
        "format": "json",
        "stream": False
    },
    timeout=90
)
print("Keys:", list(r.json().keys()))
print("Message:", r.json().get("message"))
print("Done reason:", r.json().get("done_reason"))
