import asyncio
import sys
import json
from app.llm import get_llm_provider
from app.schemas.goal import GoalUnderstandRequest
from app.services.goal_service import goal_service

async def main():
    print("--- 1. Testing LLM Health Check ---", flush=True)
    provider = get_llm_provider()
    health = await provider.health_check()
    print("Health result:", json.dumps(health, indent=2), flush=True)
    if not health.get("available"):
        print("ERROR: LLM is not available!", flush=True)
        sys.exit(1)

    print("\n--- 2. Testing Real Goal Understanding (English Goal) ---", flush=True)
    print("Sending goal to Ollama qwen3:4b (streaming tokens in background)...", flush=True)
    req_en = GoalUnderstandRequest(
        goal="Organize a 30-minute sync meeting with Alice and Bob next Tuesday at 2 PM to review quarterly budget, and email them the calendar invite.",
        language="en"
    )
    res_en = await goal_service.understand_goal(req_en)
    print("\nSUCCESS! Goal understanding result (EN):", flush=True)
    print(json.dumps(res_en.model_dump(), indent=2, default=str), flush=True)

    print("\n--- 3. Testing Real Goal Understanding (Multilingual - Hindi) ---", flush=True)
    print("Sending Hindi goal to Ollama qwen3:4b...", flush=True)
    req_hi = GoalUnderstandRequest(
        goal="अगले सप्ताह की टीम बैठक के लिए एजेंडा तैयार करें और सभी सदस्यों को ईमेल भेजें।",
        language="hi"
    )
    res_hi = await goal_service.understand_goal(req_hi)
    print("\nSUCCESS! Goal understanding result (HI):", flush=True)
    print(json.dumps(res_hi.model_dump(), indent=2, default=str), flush=True)

    print("\nAll tests passed successfully!", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
