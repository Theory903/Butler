# Testing Strategy

> **For:** QA, Engineering  
> **Status:** Draft  
> **Version:** 1.0

---

## 1. Test Pyramid

```
        ┌─────────────┐
        │     E2E     │  ← Few, slow, expensive
        ├─────────────┤
        │  Integration│  ← More, medium
        ├─────────────┤
        │    Unit     │  ← Many, fast, cheap
        └─────────────┘
```

---

## 2. Test Types

### 2.1 Unit Tests

| Target | Coverage | Tools |
|--------|----------|-------|
| Core logic | >80% | pytest, unittest |
| ML models | >70% | pytest |
| Utilities | >90% | pytest |

### 2.2 Integration Tests

| Service | Tests | Tools |
|---------|-------|-------|
| Gateway → Orchestrator | 20 | pytest |
| Orchestrator → Memory | 15 | pytest |
| Orchestrator → Tools | 10 | pytest |

### 2.3 E2E Tests

| Flow | Scenarios |
|------|-----------|
| Send message | 5 |
| Set reminder | 3 |
| Voice input | 4 |

---

## 3. Load Testing

### 3.1 Tools

- k6 (primary)
- Locust (alternative)

### 3.2 Scenarios

```yaml
# load-test.js
export default function() {
  // Simple chat
  http.post('/api/v1/chat', {
    message: 'test',
    user_id: 'test-user'
  });
}
```

### 3.3 Targets

| Metric | Target |
|--------|--------|
| RPS | 10K |
| P95 latency | <1s |
| Error rate | <1% |

---

## 4. Test Data

### 4.1 Synthetic Data

- 10K users
- 100K messages
- 1K workflows

### 4.2 Fixtures

```python
@pytest.fixture
def user():
    return {
        "id": "test-user-123",
        "email": "test@butler.lasmoid.ai",
        "preferences": {}
    }
```

---

## 5. CI/CD Integration

### 5.1 PR Checks

```yaml
- lint
- typecheck
- unit tests
- coverage check (>70%)
```

### 5.2 Merge Checks

- All PR checks pass
- Integration tests pass
- Security scan clean

---

*Document owner: QA Lead*  
*Last updated: 2026-04-15*