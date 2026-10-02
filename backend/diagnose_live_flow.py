import asyncio
import httpx
import json

BASE_URL = "http://127.0.0.1:8000"

async def main():
    async with httpx.AsyncClient(timeout=180.0) as client:
        # 1. Login test user
        login_res = await client.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "bhar180107@gmail.com", "password": "password123"}
        )
        print("Login status:", login_res.status_code)
        if login_res.status_code != 200:
            print("Login failed:", login_res.text)
            return
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Check connections
        conn_res = await client.get(f"{BASE_URL}/api/connections", headers=headers)
        print("Connections status:", conn_res.status_code)
        connections = conn_res.json()
        mcp_conns = [c for c in connections if c.get("app_id") == "mcp"]
        print(f"Found {len(mcp_conns)} MCP connection(s):")
        for c in mcp_conns:
            print(" - ID:", c.get("id"), "Status:", c.get("status"), "Config:", c.get("config"), "Perms:", c.get("permissions"))
            # Run health check
            h_res = await client.get(f"{BASE_URL}/api/connections/{c['id']}/health", headers=headers)
            print("   Health check:", h_res.status_code, h_res.json())

        # 3. Test Goal Understanding
        goal_text = "Create a note titled 'Relay Autonomous Test' with the content 'Validation verified' and verify that the note was created."
        print("\n--- Testing Goal Understanding ---")
        und_res = await client.post(f"{BASE_URL}/api/goals/understand", headers=headers, json={"goal": goal_text})
        print("Understand status:", und_res.status_code)
        if und_res.status_code != 200:
            print("Understand failed:", und_res.text)
            return

        und_data = und_res.json()
        goal_id = und_data.get("goal_id")
        understanding = und_data.get("understanding", {})
        print("Goal ID:", goal_id)
        print("Objective:", understanding.get("objective"))
        print("Desired outcome:", understanding.get("desired_outcome"))
        print("Required capabilities:", understanding.get("required_capabilities"))

        # 4. Generate Plan
        print("\n--- Generating Plan ---")
        plan_gen_res = await client.post(f"{BASE_URL}/api/plans/generate", headers=headers, json={"goal_id": goal_id})
        print("Plan generation status:", plan_gen_res.status_code)
        if plan_gen_res.status_code != 200:
            print("Plan generation failed:", plan_gen_res.text)
            return

        plan_data = plan_gen_res.json()
        plan_id = plan_data.get("id")
        print("Plan ID:", plan_id)
        print("Missing capabilities:", plan_data.get("missing_capabilities"))
        print("All tools available:", plan_data.get("all_tools_available"))
        tasks = plan_data.get("tasks", [])
        print(f"Plan has {len(tasks)} tasks:")
        for t in tasks:
            print(f" - Task {t.get('order')}: {t.get('title')} [Capability: {t.get('capability_id')}, Tool: {t.get('selected_tool_id')} ({t.get('selected_tool_name')}), Risk: {t.get('risk_level')}, Approval: {t.get('requires_approval')}]")

        # 5. Execute Plan
        print("\n--- Starting Execution ---")
        exec_start_res = await client.post(f"{BASE_URL}/api/executions/start", headers=headers, json={"plan_id": plan_id})
        print("Execution start status:", exec_start_res.status_code)
        if exec_start_res.status_code != 200:
            print("Execution start failed:", exec_start_res.text)
            return

        exec_data = exec_start_res.json()
        exec_id = exec_data.get("id")
        print("Execution ID:", exec_id, "Status:", exec_data.get("status"))

        # Poll execution status
        print("\n--- Monitoring Execution ---")
        for _ in range(30):
            await asyncio.sleep(2)
            st_res = await client.get(f"{BASE_URL}/api/executions/{exec_id}", headers=headers)
            if st_res.status_code == 200:
                e_info = st_res.json()
                print(f"Status: {e_info.get('status')}, Outcome: {e_info.get('outcome')}, Progress: {e_info.get('progress')}, Tasks: {len(e_info.get('tasks', []))}")
                if e_info.get("status") in ("completed", "failed", "awaiting_approval", "cancelled"):
                    print("Terminal or paused status reached:", e_info.get("status"))
                    print("Summary:", e_info.get("outcome_summary"))
                    for tk in e_info.get("tasks", []):
                        print(f"  * Task {tk.get('order')}: {tk.get('title')} -> {tk.get('status')} (tool: {tk.get('selected_tool_id')})")
                    break

if __name__ == "__main__":
    asyncio.run(main())
