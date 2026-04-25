import asyncio
import uuid

import httpx

BASE_URL = "http://localhost:8000/api/v1"


async def verify_system():
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/health/ready")
            if resp.status_code != 200:
                return
        except Exception:
            return

        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "Password123!"

        # 1. Register
        resp = await client.post(
            f"{BASE_URL}/auth/register",
            json={"email": test_email, "password": test_password, "display_name": "Test User"},
        )
        if resp.status_code != 201:
            return

        # 2. Login
        resp = await client.post(
            f"{BASE_URL}/auth/login", json={"email": test_email, "password": test_password}
        )
        if resp.status_code != 200:
            return

        auth_data = resp.json()
        access_token = auth_data["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        # 3. Me
        resp = await client.get(f"{BASE_URL}/auth/me", headers=headers)
        if resp.status_code != 200:
            return
        resp.json()

        # Chat
        resp = await client.post(
            f"{BASE_URL}/chat",
            headers=headers,
            json={"message": "Hello Butler, who are you?", "session_id": "test-session-1"},
        )
        if resp.status_code != 200:
            # Check if it was 200 but returned an error JSON
            pass
        else:
            resp.json()

        # Store
        fact = "The user likes coffee with no sugar."
        resp = await client.post(
            f"{BASE_URL}/memory/store",
            headers=headers,
            json={
                "content": {"text": fact, "source": "verification_test"},
                "memory_type": "preference",
            },
        )
        if resp.status_code == 200 or resp.status_code == 201:
            pass
        else:
            pass

        # Recall
        resp = await client.post(
            f"{BASE_URL}/memory/recall",
            headers=headers,
            json={"query": "What kind of coffee does the user like?", "limit": 5},
        )
        if resp.status_code != 200:
            pass
        else:
            recalled = resp.json()
            (len(recalled) if isinstance(recalled, list) else len(recalled.get("results", [])))

        # Channels
        resp = await client.get(f"{BASE_URL}/channels", headers=headers)
        if resp.status_code != 200:
            if resp.status_code == 404:
                pass
            else:
                pass
        else:
            resp.json()

        # Test tool use via chat
        resp = await client.post(
            f"{BASE_URL}/chat",
            headers=headers,
            json={
                "message": "Give me a detailed report on system cpu and disk load",
                "session_id": "agent-test-session",
            },
        )
        if resp.status_code != 200:
            pass
        else:
            data = resp.json()
            response = data.get("response", "")

            if "error" in response.lower() or "Butler encountered" in response:
                pass

            # Simple heuristic check for metric reporting
            diagnostics = ["cpu", "memory", "load", "node", "status", "uptime"]
            found = [d for d in diagnostics if d in response.lower()]

            if found:
                pass
            else:
                pass


if __name__ == "__main__":
    asyncio.run(verify_system())
