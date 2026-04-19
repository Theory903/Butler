# First Working Flow - End-to-End Execution

> **Status:** Executable  
> **Purpose:** Your first working system - prove the loop works

---

## Flow: "Send Message"

```
User types: "Hello" → Butler responds with "Hi! How can I help?"
```

This is the **minimum viable loop**. Everything else builds on this.

---

## Step-by-Step Execution

### Step 1: User Input
```
Mobile App sends HTTP POST /api/v1/chat
Body: {"message": "Hello", "session_id": "abc123"}
```

### Step 2: Gateway (port 8000)
```
1. Receive request
2. Validate auth token (JWT)
3. Extract message + session_id
4. Forward to Orchestrator
5. Return 202 Accepted
```

**Code:**
```python
# gateway/main.py
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ChatRequest(BaseModel):
    message: str
    session_id: str

@app.post("/api/v1/chat")
async def chat(req: ChatRequest, authorization: str = Header(...)):
    # 1. Validate JWT
    user_id = validate_token(authorization)
    
    # 2. Forward to orchestrator
    result = await orchestrator_client.post("/process", {
        "message": req.message,
        "session_id": req.session_id,
        "user_id": user_id
    })
    
    # 3. Return immediately (async)
    return {"status": "processing", "request_id": result["request_id"]}
```

### Step 3: Orchestrator (port 8002)
```
1. Receive message + user_id + session_id
2. Classify intent (simple message → direct response)
3. Build context from Memory
4. Execute response
5. Return response
```

**Code:**
```python
# orchestrator/service.py
from fastapi import FastAPI
import asyncio

app = FastAPI()

@app.post("/process")
async def process(request: dict):
    message = request["message"]
    user_id = request["user_id"]
    session_id = request["session_id"]
    
    # 1. Classify intent
    intent = await classify_intent(message)
    
    # 2. Handle simple message
    if intent.type == "greeting":
        response = "Hi! How can I help you today?"
    
    # 3. Save to memory
    await memory_service.save(session_id, "user", message)
    await memory_service.save(session_id, "assistant", response)
    
    return {
        "response": response,
        "intent": intent.type
    }
```

### Step 4: Memory (port 8003)
```
Simple session存储:
- session_id → [messages]
- Key: session_id, Value: list of (role, content, timestamp)
```

**Code:**
```python
# memory/service.py
import redis
import json

class SessionStore:
    def __init__(self):
        self.redis = redis.Redis(host="localhost", port=6379)
    
    async def save(self, session_id: str, role: str, content: str):
        key = f"session:{session_id}"
        entry = json.dumps({"role": role, "content": content})
        self.redis.rpush(key, entry)
    
    async def get_history(self, session_id: str) -> list:
        key = f"session:{session_id}"
        return self.redis.lrange(key, 0, -1)
```

### Step 5: Response
```
Gateway → Mobile App: {"response": "Hi! How can I help you today?"}
```

---

## Complete Flow Diagram

```
┌─────────────┐     POST /api/v1/chat      ┌─────────────┐
│   Mobile   │ ────────────────────────→ │ Gateway   │
│    App    │                       │  (8000)   │
└───────��─────┘                       └─────┬─────┘
                                            │
                                     Forward /process
                                            │
                                            ▼
┌─────────────┐     /process + intent         ┌─────────────┐
│  Memory    │ ←───────────────────────  │Orchestrator│
│  (8003)    │   save/get history      │ (8002)    │
└─────────────┘                       └─────┬─────┘
                                            │
                                     Intent: greeting
                                     Response: "Hi! How can I help?"
                                            │
                                            ▼
                                      ┌───────────┐
                                      │ Response  │
                                      │ to Mobile │
                                      └───────────┘
```

---

## Files to Create (First Iteration)

| File | Purpose |
|------|---------|
| `gateway/main.py` | Basic HTTP server |
| `gateway/routes.py` | /api/v1/chat endpoint |
| `orchestrator/service.py` | Intent classification + response |
| `orchestrator/intent.py` | Simple keyword-based classifier |
| `memory/service.py` | Redis session store |
| `docker-compose.yml` | Run all services |

---

## Test It

```bash
# 1. Start services
docker-compose up -d

# 2. Login (get token)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "test123"}'

# Returns: {"token": "eyJhbGciOiJIUzI1NiIs..."}

# 3. Send message
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "session_id": "abc123"}'

# Returns: {"response": "Hi! How can I help you today?"}
```

---

## Success Criteria

- [ ] POST /api/v1/chat returns response within 500ms
- [ ] Session stores user message + assistant response
- [ ] Same session_id returns conversation history
- [ ] Invalid token returns 401

---

*Next: Add a tool (e.g., "send_message" to external API)*