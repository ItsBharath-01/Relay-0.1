import sys
import asyncio
import json
import functools
import httpx

# Ensure unbuffered and utf-8 output on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

print = functools.partial(print, flush=True)

BASE_URL = "http://127.0.0.1:8000/api"
USER_EMAIL = "testuser@example.com"
USER_PASSWORD = "Password123!"

async def run_test(goal_text: str, test_label: str):
    print(f"\n=======================================================")
    print(f"STARTING {test_label}: '{goal_text}'")
    print(f"=======================================================\n")

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Login
        login_res = await client.post(f"{BASE_URL}/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        auth_data = login_res.json()
        token = auth_data["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[AUTH] Logged in as: {auth_data['user']['email']} (id: {auth_data['user']['id']})")

        # 2. Goal Understanding
        print(f"\n[PHASE 1: GOAL UNDERSTANDING]")
        und_res = await client.post(
            f"{BASE_URL}/goals/understand",
            json={"goal": goal_text, "language": "en"},
            headers=headers
        )
        assert und_res.status_code == 200, f"Understand failed: {und_res.text}"
        und_data = und_res.json()
        goal_id = und_data["goal_id"]
        print(f"Goal ID: {goal_id}")
        print(f"Objective: {und_data['understanding']['objective']}")
        print(f"Required Capabilities: {und_data['understanding']['required_capabilities']}")
        print(f"Clarification Needed: {und_data['understanding']['clarification_needed']}")
        print(f"LLM Metadata: {json.dumps(und_data.get('provider_meta', {}), indent=2)}")

        # 3. Planning
        print(f"\n[PHASE 2: PLANNING & DECOMPOSITION]")
        plan_res = await client.post(
            f"{BASE_URL}/plans/generate",
            json={"goal_id": goal_id},
            headers=headers
        )
        assert plan_res.status_code == 200, f"Plan generation failed: {plan_res.text}"
        plan_data = plan_res.json()
        plan_id = plan_data["id"]
        print(f"Plan ID: {plan_id}")
        print(f"All Tools Available: {plan_data['all_tools_available']}")
        print(f"Missing Capabilities: {plan_data['missing_capabilities']}")
        for t in plan_data["tasks"]:
            print(f" - Task {t['order']}: {t['title']}")
            print(f"   Capability: {t['capability_id']}")
            print(f"   Risk: {t['risk_level']} (Approval required: {t['requires_approval']})")
            print(f"   Selected Tool: {t['selected_tool_id']} ({t.get('selected_tool_name')})")
            print(f"   Action: {t.get('action')}, Params: {t.get('params')}")

        # 4. Start Execution and Listen to SSE Stream
        print(f"\n[PHASE 3: EXECUTION & SSE EVENT STREAM]")
        exec_start_res = await client.post(
            f"{BASE_URL}/executions/start",
            json={"plan_id": plan_id},
            headers=headers
        )
        assert exec_start_res.status_code == 200, f"Execution start failed: {exec_start_res.text}"
        exec_data = exec_start_res.json()
        exec_id = exec_data["id"]
        print(f"Execution ID: {exec_id} (Status: {exec_data['status']})")

        events_captured = []

        # Connect to SSE stream
        sse_url = f"{BASE_URL}/executions/{exec_id}/events?token={token}"
        async with client.stream("GET", sse_url, headers=headers, timeout=120.0) as stream:
            async for line in stream.aiter_lines():
                if not line.strip():
                    continue
                if line.startswith("data:"):
                    raw_data = line[5:].strip()
                    try:
                        ev = json.loads(raw_data)
                        events_captured.append(ev)
                        ev_type = ev.get("type")
                        ev_msg = ev.get("message")
                        print(f"  [EVENT #{ev.get('sequence', '?')}] {ev_type:<20} | {ev_msg}")
                        if ev.get("payload"):
                            p = ev["payload"]
                            if ev_type == "tool_discovery":
                                for c in p.get("candidates", []):
                                    print(f"    * Candidate: {c['tool_name']} (type: {c['tool_type']}) - Passed all: {c['passed_all']} - Ruled out: {c.get('ruled_out_reason')}")
                            elif ev_type == "risk_classified":
                                print(f"    * Risk: {p.get('risk_level')}, Requires approval: {p.get('requires_approval')}, Reason: {p.get('reason')}")
                            elif ev_type == "approval_required":
                                print(f"    * APPROVAL REQUESTED: {p.get('action')} target={p.get('target')} hash={p.get('payload_hash')}")
                            elif ev_type == "observation":
                                print(f"    * Observation keys: {list(p.keys()) if isinstance(p, dict) else str(p)[:60]}")
                            elif ev_type == "verification_completed":
                                print(f"    * Verification outcome: {p.get('result')}, Criterion: {p.get('criterion')}, Evidence: {p.get('evidence')}")
                            elif ev_type == "task_failed":
                                print(f"    * FAILURE DETAIL: {p}")

                        # Check if terminal event
                        if ev_type in ["execution_completed", "execution_failed"]:
                            break
                    except Exception as err:
                        print(f"  [RAW SSE] {raw_data} (err: {err})")

        # 5. Fetch final state from DB via API
        print(f"\n[PHASE 4: FINAL EXECUTION STATUS & AUDIT]")
        exec_detail_res = await client.get(f"{BASE_URL}/executions/{exec_id}", headers=headers)
        final_detail = exec_detail_res.json()
        print(f"Final Execution Status: {final_detail.get('status')}")
        print(f"Outcome: {final_detail.get('outcome')}")
        print(f"Evidence Level: {final_detail.get('evidence_level')}")
        print(f"Outcome Summary: {final_detail.get('outcome_summary')}")
        print(f"Progress: {final_detail.get('progress')}")
        print(f"Started At: {final_detail.get('started_at')}")
        print(f"Completed At: {final_detail.get('completed_at')}")

        return {
            "test_label": test_label,
            "goal": goal_text,
            "understanding": und_data,
            "plan": plan_data,
            "execution": final_detail,
            "events": events_captured
        }

async def main():
    res_a = await run_test("Play a Tamil music", "TEST A")
    res_b = await run_test("Play some Tamil songs", "TEST B")
    
    with open("live_validation_results.json", "w", encoding="utf-8") as f:
        json.dump({"test_a": res_a, "test_b": res_b}, f, indent=2)
    print("\nSaved full execution logs to live_validation_results.json")

if __name__ == "__main__":
    asyncio.run(main())
