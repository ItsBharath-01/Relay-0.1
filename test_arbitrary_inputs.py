import asyncio
import httpx

BASE_URL = "http://127.0.0.1:8000/api"
USER_EMAIL = "testuser@example.com"
USER_PASSWORD = "Password123!"

GOALS = [
    "Find the cheapest flight from NYC to London",
    "Calculate 15% tip on 85 dollars",
    "Summarize this document about quarterly earnings",
    "Send a message to the engineering team on Slack"
]

async def test_diverse_inputs():
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Login
        login_res = await client.post(f"{BASE_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        print("Testing arbitrary goals (Intent -> Capability -> Tool Selection):")
        for g in GOALS:
            print(f"\n--- Goal: '{g}' ---")
            und_res = await client.post(
                f"{BASE_URL}/goals/understand",
                json={"goal": g, "language": "en"},
                headers=headers
            )
            und = und_res.json()["understanding"]
            print(f"Objective: {und['objective']}")
            print(f"Desired Outcome: {und.get('desired_outcome')}")
            print(f"Success Criteria: {und.get('success_criteria')}")
            print(f"Required Capabilities: {und.get('required_capabilities')}")

            plan_res = await client.post(
                f"{BASE_URL}/plans/generate",
                json={"goal_id": und_res.json()["goal_id"]},
                headers=headers
            )
            plan = plan_res.json()
            print(f"Tasks Generated: {len(plan['tasks'])}")
            for t in plan["tasks"]:
                print(f"  * {t['title']} -> Cap: {t['capability_id']} -> Selected: {t['selected_tool_id']}")

if __name__ == "__main__":
    asyncio.run(test_diverse_inputs())
