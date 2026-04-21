import asyncio
import httpx
import json
import sys
import uuid
from datetime import datetime

BASE_URL = "http://localhost:8000"
TEST_ACCOUNT = {
    "email": f"test_{uuid.uuid4().hex[:8]}@butler.ai",
    "password": "OraclePassword123!",
    "display_name": "Verification Bot"
}

async def verify_endpoint(client, method, path, name, data=None, headers=None, expected_status=200):
    print(f"Testing {name:.<40}", end=" ", flush=True)
    try:
        if method == "GET":
            resp = await client.get(path, headers=headers)
        else:
            resp = await client.post(path, json=data, headers=headers)
        
        if resp.status_code == expected_status:
            print("OK")
            return resp.json()
        else:
            print(f"FAILED (Status: {resp.status_code})")
            print(f"Response: {resp.text}")
            return None
    except Exception as e:
        print(f"ERROR ({str(e)})")
        return None

async def main():
    print(f"\nButler API Verification Suite - {datetime.now().isoformat()}")
    print("="*60)
    
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # Phase 1: Health Probes
        print("\n[Phase 1] Infrastructure Health")
        await verify_endpoint(client, "GET", "/health", "Legacy Health")
        await verify_endpoint(client, "GET", "/health/live", "Liveness Probe")
        await verify_endpoint(client, "GET", "/health/ready", "Readiness Probe")
        await verify_endpoint(client, "GET", "/health/startup", "Startup Probe")

        # Phase 2: Identity & Auth
        print("\n[Phase 2] Identity & Authentication")
        reg_data = await verify_endpoint(
            client, "POST", "/api/v1/auth/register", "Account Registration", 
            data=TEST_ACCOUNT, expected_status=201
        )
        
        if not reg_data:
            print("Stopping test: Registration failed.")
            return

        login_data = await verify_endpoint(
            client, "POST", "/api/v1/auth/login", "Account Login", 
            data={"email": TEST_ACCOUNT["email"], "password": TEST_ACCOUNT["password"]}
        )
        
        if not login_data:
            print("Stopping test: Login failed.")
            return

        token = login_data["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        
        await verify_endpoint(client, "GET", "/api/v1/auth/me", "Identity Verification", headers=auth_headers)

        # Phase 3: Core Cognitive
        print("\n[Phase 3] Cognitive Flow (Chat)")
        chat_req = {
            "message": "Hello Butler, run a system self-check.",
            "session_id": f"verify-{uuid.uuid4().hex[:8]}",
            "stream": False
        }
        await verify_endpoint(client, "POST", "/api/v1/chat", "Synchronous Chat", data=chat_req, headers=auth_headers)

        # Phase 4: Service Surface
        print("\n[Phase 4] Service Surface Sanity")
        await verify_endpoint(client, "GET", "/api/v1/channels", "Hermes Channel Directory", headers=auth_headers)
        await verify_endpoint(client, "GET", "/api/v1/memory/profile", "Memory Profile Access", headers=auth_headers)

    print("\n" + "="*60)
    print("Verification Completed.")

if __name__ == "__main__":
    asyncio.run(main())
