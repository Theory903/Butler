import asyncio
import httpx
import uuid
import sys
import json
from datetime import datetime

BASE_URL = "http://localhost:8000/api/v1"

async def verify_system():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("=== Phase 0: Infrastructure Health ===")
        try:
            resp = await client.get(f"{BASE_URL}/health/ready")
            print(f"[READY] {resp.status_code}: {resp.json()}")
            if resp.status_code != 200:
                print("!! System not ready. Aborting.")
                return
        except Exception as e:
            print(f"!! Health check failed: {e}")
            return

        print("\n=== Phase 1: Identity & Security ===")
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "Password123!"
        
        # 1. Register
        print(f"Registering {test_email}...")
        resp = await client.post(f"{BASE_URL}/auth/register", json={
            "email": test_email,
            "password": test_password,
            "display_name": "Test User"
        })
        if resp.status_code != 201:
            print(f"!! Registration failed ({resp.status_code}): {resp.text}")
            return
        print("[OK] Registration successful.")

        # 2. Login
        print("Logging in...")
        resp = await client.post(f"{BASE_URL}/auth/login", json={
            "email": test_email,
            "password": test_password
        })
        if resp.status_code != 200:
            print(f"!! Login failed ({resp.status_code}): {resp.text}")
            return
        
        auth_data = resp.json()
        access_token = auth_data["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        print("[OK] Login successful. JWT retrieved.")

        # 3. Me
        print("Verifying /auth/me...")
        resp = await client.get(f"{BASE_URL}/auth/me", headers=headers)
        if resp.status_code != 200:
            print(f"!! /auth/me failed ({resp.status_code}): {resp.text}")
            return
        user_info = resp.json()
        print(f"[OK] Identity verified: {user_info['principal']['email']} (Principal: {user_info['principal']['id']})")

        print("\n=== Phase 2: Intelligence & Orchestration ===")
        # Chat
        print("Sending message to gateway...")
        resp = await client.post(f"{BASE_URL}/chat", headers=headers, json={
            "message": "Hello Butler, who are you?",
            "session_id": "test-session-1"
        })
        if resp.status_code != 200:
             # Check if it was 200 but returned an error JSON
             print(f"!! Chat failed ({resp.status_code}): {resp.text}")
        else:
            chat_resp = resp.json()
            print(f"[OK] Chat response: {chat_resp}")

        print("\n=== Phase 3: Durable Memory ===")
        # Store
        print("Storing memory...")
        fact = "The user likes coffee with no sugar."
        resp = await client.post(f"{BASE_URL}/memory/store", headers=headers, json={
            "content": {"text": fact, "source": "verification_test"},
            "memory_type": "preference"
        })
        if resp.status_code == 200 or resp.status_code == 201:
            print("[OK] Memory stored successfully.")
        else:
            print(f"!! Memory store failed ({resp.status_code}): {resp.text}")

        # Recall
        print("Recalling memory...")
        resp = await client.post(f"{BASE_URL}/memory/recall", headers=headers, json={
            "query": "What kind of coffee does the user like?",
            "limit": 5
        })
        if resp.status_code != 200:
             print(f"!! Memory recall failed ({resp.status_code}): {resp.text}")
        else:
            recalled = resp.json()
            num_results = len(recalled) if isinstance(recalled, list) else len(recalled.get("results", []))
            print(f"[OK] Memory recalled: {num_results} results found.")

        print("\n=== Phase 4: Tools & Channels ===")
        # Channels
        print("Checking channel discovery...")
        resp = await client.get(f"{BASE_URL}/channels", headers=headers)
        if resp.status_code != 200:
            if resp.status_code == 404:
                print("!! /channels not found (Endpoint might be under /admin or /acp)")
            else:
                print(f"!! Channels failed ({resp.status_code}): {resp.text}")
        else:
            channels = resp.json()
            print(f"[OK] Discovered {len(channels)} channels.")

        print("\n=== Phase 5: Agentic Autonomy ===")
        # Test tool use via chat
        print("Testing autonomous tool selection (system stats)...")
        resp = await client.post(f"{BASE_URL}/chat", headers=headers, json={
            "message": "Give me a detailed report on system cpu and disk load",
            "session_id": "agent-test-session"
        })
        if resp.status_code != 200:
            print(f"!! Agentic chat failed ({resp.status_code}): {resp.text}")
        else:
            data = resp.json()
            response = data.get("response", "")
            
            if "error" in response.lower() or "Butler encountered" in response:
                print(f"[DEBUG] Error metadata: {data.get('metadata')}")
            
            # Simple heuristic check for metric reporting
            diagnostics = ["cpu", "memory", "load", "node", "status", "uptime"]
            found = [d for d in diagnostics if d in response.lower()]
            
            if found:
                print(f"[OK] Agent response: {response[:100]}...")
                print(f"[OK] Found diagnostic metrics: {', '.join(found)}")
            else:
                print(f"[OK] Agent response: {response[:100]}...")
                print(f"?? Could not confirm metric extraction from response text.")

        print("\n=== VERIFICATION COMPLETE ===")

if __name__ == "__main__":
    asyncio.run(verify_system())
