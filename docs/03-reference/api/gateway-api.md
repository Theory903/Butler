# Butler API Contracts

> **For:** Engineers, External Integrators  
> **Status:** Draft  
> **Version:** 1.0

---

## Base URL

```
Production: https://api.butler.ai/v1
Development: http://localhost:8000/v1
```

---

## Authentication

### JWT Bearer Token

```yaml
Header:
  Authorization: Bearer <jwt_token>
  
Errors:
  - 401: Invalid or expired token
  - 403: Insufficient permissions
```

### Refresh Token

```yaml
POST /auth/refresh
  Request:
    { "refresh_token": "string" }
  Response:
    { "access_token": "string", "expires_in": 3600 }
```

---

## Gateway API

### Health

```yaml
GET /health
  Response:
    { "status": "healthy", "services": {} }

GET /health/all
  Response:
    { 
      "gateway": "healthy",
      "orchestrator": "healthy",
      "memory": "healthy",
      "ml": "healthy"
    }
```

### Chat

```yaml
POST /chat
  Auth: Required
  Request:
    {
      "message": "string",
      "context": {}
    }
  Response:
    {
      "response": "string",
      "intent": "string",
      "actions": []
    }

WebSocket: /ws/chat
  Client → { "message": "string", "context": {} }
  Server → { "chunk": "string", "done": true }
```

### Rate Limits

```yaml
Response Headers:
  X-RateLimit-Limit: 100
  X-RateLimit-Remaining: 95
  X-RateLimit-Reset: 1640000000
```

---

## Orchestrator API

### Intent

```yaml
POST /orchestrator/intent
  Request:
    { "text": "string", "context": {} }
  Response:
    {
      "intent": "send_message",
      "confidence": 0.95,
      "entities": {}
    }
```

### Execute

```yaml
POST /orchestrator/execute
  Request:
    {
      "intent": "string",
      "entities": {},
      "context": {}
    }
  Response:
    {
      "execution_id": "uuid",
      "status": "completed",
      "result": {}
    }

GET /orchestrator/execute/{execution_id}
  Response:
    { "status": "completed", "result": {}, "error": null }
```

### Context

```yaml
POST /orchestrator/context
  Request:
    { "user_id": "uuid" }
  Response:
    {
      "recent": [],
      "preferences": {},
      "relationships": []
    }
```

---

## Memory API

### Graph

```yaml
POST /memory/graph
  Auth: Required
  Request:
    {
      "operation": "create",  # create, read, update, delete
      "entity": { "type": "person", "name": "string" }
    }
  Response:
    { "id": "uuid" }

GET /memory/graph/{entity_id}
  Response:
    { "id": "uuid", "type": "person", "connections": [] }
```

### Semantic Search

```yaml
POST /memory/search
  Request:
    { "query": "string", "limit": 5 }
  Response:
    { "results": [{ "id": "uuid", "score": 0.95, "text": "..." }] }
```

### Preferences

```yaml
GET /memory/preferences/{user_id}
  Response:
    { "notifications": true, "theme": "dark", "language": "en" }

PATCH /memory/preferences/{user_id}
  Request:
    { "theme": "light" }
  Response:
    { "updated": true }
```

### Context Cache

```yaml
GET /memory/context/{session_id}
  Response:
    { "messages": [], "state": {} }

POST /memory/context/{session_id}
  Request:
    { "key": "last_action", "value": "send_message" }
  Response:
    { "cached": true }
```

---

## ML API

### Intent Classification

```yaml
POST /ml/intent/classify
  Request:
    { "text": "string", "context": {} }
  Response:
    {
      "intent": "send_message",
      "confidence": 0.95,
      "alternatives": []
    }
```

### Embeddings

```yaml
POST /ml/embed
  Request:
    { "text": "string or array", "model": "bge-large" }
  Response:
    { "embeddings": [[0.1, ...]], "model": "bge-large" }
```

### Recommendations

```yaml
POST /ml/recommend
  Request:
    { "user_id": "uuid", "context": {}, "limit": 5 }
  Response:
    { "recommendations": [{ "action": "...", "score": 0.9 }] }
```

### Prediction

```yaml
POST /ml/predict/next_action
  Request:
    { "user_id": "uuid", "action_history": [] }
  Response:
    { "predictions": [{ "action": "...", "probability": 0.45 }] }
```

---

## Tools API

### List Tools

```yaml
GET /tools
  Response:
    { "tools": [{ "name": "send_message", "description": "..." }] }
```

### Execute Tool

```yaml
POST /tools/execute
  Auth: Required (tool permission)
  Request:
    { "tool": "send_message", "params": {}, "user_id": "uuid" }
  
  Response:
    { "success": true, "result": {}, "verification": {} }
  
  Errors:
    - 400: Invalid parameters
    - 403: Permission denied
    - 408: Execution timeout
    - 429: Rate limited
```

### Tool Schema

```yaml
GET /tools/{tool_name}/schema
  Response:
    {
      "name": "send_message",
      "input_schema": {},
      "output_schema": {},
      "timeout": 10
    }
```

---

## Audio API

### Speech to Text

```yaml
POST /audio/stt
  Request:
    { "audio_data": "base64", "language": "en" }
  Response:
    { "transcript": "string", "confidence": 0.95 }

WebSocket: /ws/audio
  Stream audio chunks → Get streaming transcript
```

### Text to Speech

```yaml
POST /audio/tts
  Request:
    { "text": "string", "voice": "en-US-AriaNeural" }
  Response:
    { "audio_data": "base64" }
```

### Wake Word

```yaml
POST /audio/wake/validate
  Request:
    { "audio_data": "base64" }
  Response:
    { "detected": true, "confidence": 0.92 }
```

---

## Vision API

### Detect Objects

```yaml
POST /vision/detect
  Request:
    { "image_data": "base64" }
  Response:
    { "objects": [{ "class": "button", "bbox": [], "confidence": 0.9 }] }
```

### OCR

```yaml
POST /vision/ocr
  Request:
    { "image_data": "base64" }
  Response:
    { "text": "string", "blocks": [] }
```

### Screen Parse

```yaml
POST /vision/screen-parse
  Request:
    { "image_data": "base64" }
  Response:
    { "elements": [], "screen_type": "login", "actions": [] }
```

---

## Data API

### Users

```yaml
POST /data/users
  Request:
    { "email": "string", "name": "string" }
  Response:
    { "id": "uuid", "email": "...", "created_at": "..." }

GET /data/users/{user_id}
  Response:
    { "id": "uuid", "settings": {} }
```

### Sessions

```yaml
POST /data/sessions
  Request:
    { "user_id": "uuid" }
  Response:
    { "id": "uuid", "expires_at": "..." }

GET /data/sessions/{session_id}
  Response:
    { "id": "...", "context": {} }
```

### Workflows

```yaml
POST /data/workflows
  Request:
    { "user_id": "uuid", "name": "string", "definition": {} }
  Response:
    { "id": "uuid", "status": "active" }

GET /data/workflows
  Query: user_id, status
  Response:
    { "workflows": [...] }
```

---

## Error Responses

### Standard Error Format

```yaml
{
  "error": {
    "code": "TOOL_001",
    "message": "Tool execution failed",
    "details": {}
  }
}
```

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| VALIDATION_001 | 400 | Invalid parameters |
| AUTH_001 | 401 | Invalid token |
| AUTH_002 | 401 | Expired token |
| PERMISSION_001 | 403 | Access denied |
| NOT_FOUND_001 | 404 | Resource not found |
| RATE_001 | 429 | Rate limited |
| INTERNAL_001 | 500 | Internal error |
| SERVICE_001 | 503 | Service unavailable |

---

*Document owner: API Team*  
*Last updated: 2026-04-16*