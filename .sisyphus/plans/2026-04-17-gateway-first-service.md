# Gateway Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement Step 1: Gateway basic API service - first running service in Butler build sequence

**Architecture:** FastAPI standalone service, following KISS principles exactly as documented
**Tech Stack:** FastAPI, Uvicorn, Python 3.13

**Preconditions:**
✅ Hermes full assimilation completed
✅ All imports working correctly
✅ All 6 verification tests passing
✅ Butler is implementation-ready

---

## Task 1: Create Gateway service directory

**Files:**
- Create: `gateway/`
- Create: `gateway/requirements.txt`

**Step 1: Create directory**
```bash
mkdir -p gateway
```

**Step 2: Create requirements.txt**
```txt
fastapi>=0.115.0
uvicorn>=0.30.0
httpx>=0.27.0
python-jose[cryptography]>=3.3.0
python-multipart>=0.0.12
```

**Step 3: Commit**
```bash
git add gateway/requirements.txt
git commit -m "feat(gateway): add requirements"
```

---

## Task 2: Implement FastAPI app base

**Files:**
- Create: `gateway/main.py`

**Step 1: Write failing test**
```bash
cat > gateway/test_main.py << 'EOF'
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_chat_echo_endpoint():
    response = client.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert response.json() == {"response": "Echo: hello"}
EOF
```

**Step 2: Run test to verify it fails**
```bash
cd gateway && python -m pytest test_main.py -v
```
Expected: FAIL with import error

**Step 3: Implement minimal gateway main.py**
```python
from fastapi import FastAPI

app = FastAPI(title="Butler Gateway", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/v1/chat")
def chat(request: dict):
    return {"response": f"Echo: {request.get('message', '')}"}
```

**Step 4: Run test to verify it passes**
```bash
cd gateway && python -m pytest test_main.py -v
```
Expected: 2/2 tests PASS

**Step 5: Commit**
```bash
git add gateway/main.py gateway/test_main.py
git commit -m "feat(gateway): implement base service with health and echo endpoints"
```

---

## Task 3: Add Dockerfile

**Files:**
- Create: `gateway/Dockerfile`

**Step 1: Write Dockerfile**
```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

**Step 2: Test Docker build**
```bash
cd gateway && docker build -t butler-gateway .
```
Expected: Build completes successfully

**Step 3: Commit**
```bash
git add gateway/Dockerfile
git commit -m "feat(gateway): add Dockerfile"
```

---

## Task 4: Verify running service

**Step 1: Run gateway locally**
```bash
cd gateway && uvicorn main:app --reload --port 8000
```

**Step 2: Verify endpoints work**
```bash
# Health check
curl http://localhost:8000/health

# Echo test
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hello butler"}'
```
Expected: Returns {"response": "Echo: hello butler"}

---

## Verification Checklist

✅ Gateway directory created
✅ requirements.txt added
✅ main.py implemented with health and chat endpoints
✅ Tests pass
✅ Dockerfile created
✅ Service runs locally
✅ Endpoints respond correctly

---

## Next Steps

After Gateway completion:
1. Step 2: Auth service
2. Step 3: Orchestrator service
3. Step 4: Memory service
4. Step 5: Tools service
5. Step 6: Full integration