# AI Security

> **For:** Engineering, ML Team, Security  
> **Status:** Production Required  
> **Version:** 1.0

---

## 1. AI-Specific Threats

### 1.1 OWASP Top 10 for LLMs

| Risk | Description | Mitigation |
|------|-------------|-------------|
| LLM01 | Prompt Injection | Input validation, output filtering |
| LLM02 | Insecure Output Handling | Output schema validation |
| LLM03 | Training Data Poisoning | Data provenance, validation |
| LLM04 | Model Denial of Service | Rate limiting, token budgets |
| LLM05 | Supply Chain | Model pinning, hash verification |
| LLM06 | Sensitive Information Disclosure | PII redaction, retrieval filters |
| LLM07 | Insecure Plugin Design | Tool isolation, permission checks |
| LLM08 | Excessive Agency | Human-in-loop, approval gates |
| LLM09 | Overreliance | Confidence scoring, fallback |
| LLM10 | Model Theft | Access control, watermarking |

---

## 2. Prompt Injection Defense

### 2.1 Input Sanitization

```python
class PromptInjectionDefense:
    """Defend against prompt injection attacks"""
    
    # Known injection patterns
    INJECTION_PATTERNS = [
        r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions?|rules?|prompts?)",
        r"(?:system|admin)\s*:\s*",
        r"<\s*/?script",
        r"\{\{.*\}\}",  # Template injection
        r"\[\[.*\]\]",  # Instruction brackets
        r"(?:you\s+are|pretend\s+to\s+be|imagine\s+you\s+are)",
    ]
    
    def sanitize(self, user_input: str) -> str:
        """Remove or escape injection attempts"""
        
        sanitized = user_input
        
        for pattern in self.INJECTION_PATTERNS:
            # Replace with placeholder
            sanitized = re.sub(pattern, "[FILTERED]", sanitized, flags=re.IGNORECASE)
        
        # Escape special characters
        sanitized = self.escape_special_chars(sanitized)
        
        return sanitized
    
    def detect(self, user_input: str) -> InjectionResult:
        """Detect potential injection attempts"""
        
        matches = []
        
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, user_input, re.IGNORECASE):
                matches.append(pattern)
        
        if matches:
            return InjectionResult(
                detected=True,
                confidence=len(matches) / len(self.INJECTION_PATTERNS),
                patterns=matches,
                action="flag"  # flag, block, or sanitize
            )
        
        return InjectionResult(detected=False, confidence=0.0)
```

### 2.2 Output Validation

```python
class OutputValidator:
    """Validate LLM output before action"""
    
    # Dangerous patterns in output
    DANGEROUS_PATTERNS = [
        r"DELETE\s+\w+",  # SQL delete
        r"DROP\s+\w+",     # SQL drop
        r"exec\s*\(",       # Code execution
        r"eval\s*\(",       # Code evaluation
        r"<script",         # XSS
        r"javascript:",      # XSS
        r"data:text/html",   # XSS
    ]
    
    def validate(self, output: str, context: ActionContext) -> ValidationResult:
        """Validate output before executing"""
        
        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, output, re.IGNORECASE):
                return ValidationResult(
                    valid=False,
                    reason=f"Dangerous pattern detected: {pattern}",
                    action="block"
                )
        
        # Schema validation
        if context.expected_schema:
            if not self.validate_schema(output, context.expected_schema):
                return ValidationResult(
                    valid=False,
                    reason="Output doesn't match expected schema",
                    action="block"
                )
        
        return ValidationResult(valid=True)
```

---

## 3. Tool Gating

### 3.1 Tool Access Control

```python
class ToolGating:
    """Control model access to tools"""
    
    # Tools the model can request (not execute directly)
    ALLOWED_TOOLS = {
        "read": ["search", "get_memory", "get_context"],
        "write": ["append_memory", "log_interaction"],
        "action": ["send_message", "send_email", "create_event"]
    }
    
    # Tools requiring human approval
    APPROVAL_REQUIRED = {
        "send_message": ["high_risk"],
        "payment": ["all"],
        "delete": ["all"],
        "device_control": ["lock", "camera"]
    }
    
    async def evaluate_request(
        self, 
        requested_tool: str, 
        params: dict,
        user_context: UserContext
    ) -> ToolGatingResult:
        
        # 1. Check if tool is allowed
        if requested_tool not in self.ALLOWED_TOOLS:
            return ToolGatingResult(
                allowed=False,
                reason=f"Tool {requested_tool} not in allowlist"
            )
        
        # 2. Check permission
        if not await self.has_permission(user_context, requested_tool):
            return ToolGatingResult(
                allowed=False,
                reason="User lacks permission"
            )
        
        # 3. Check approval requirement
        if requested_tool in self.APPROVAL_REQUIRED:
            risk_level = self.assess_risk(requested_tool, params)
            if risk_level in self.APPROVAL_REQUIRED[requested_tool]:
                return ToolGatingResult(
                    allowed=False,
                    reason="Requires approval",
                    requires_approval=True,
                    approval_type=risk_level
                )
        
        # 4. Validate parameters
        validated_params = await self.validate_params(requested_tool, params)
        
        return ToolGatingResult(
            allowed=True,
            params=validated_params
        )
```

---

## 4. Retrieval Safety

### 4.1 Memory Access Control

```python
class RetrievalAccessControl:
    """Control what the model can retrieve"""
    
    # Sensitive memory classes
    RESTRICTED_CLASSES = [
        "payment_info",
        "authentication",
        "security_settings",
        "private_messages"
    ]
    
    async def filter_retrieval(
        self,
        retrieved_docs: list[Document],
        query_context: QueryContext
    ) -> list[Document]:
        """Filter retrieved documents based on access"""
        
        filtered = []
        
        for doc in retrieved_docs:
            # Check if document class is restricted
            if doc.classification in self.RESTRICTED_CLASSES:
                # Only allow if task matches purpose
                if not self.task_matches_purpose(query_context.task, doc.classification):
                    continue
            
            # Check user access
            if not await self.user_can_access(query_context.user_id, doc):
                continue
            
            filtered.append(doc)
        
        return filtered
    
    def task_matches_purpose(self, task: str, doc_class: str) -> bool:
        """Check if task justifies accessing restricted class"""
        
        mappings = {
            "payment_info": ["check_payment_status", "refund"],
            "authentication": ["verify_identity", "reset_password"],
            "security_settings": ["manage_security", "view_trusted_devices"],
            "private_messages": ["read_messages", "search_messages"]
        }
        
        return task in mappings.get(doc_class, [])
```

---

## 5. Model Isolation

### 5.1 Untrusted Content Pipeline

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Untrusted  │────→│   Sanitize  │────→│   Isolate   │
│  Input      │     │   + Detect   │     │   (Lower   │
│  (Web/OCR) │     │              │     │   Trust)    │
└─────────────┘     └─────────────┘     └─────────────┘
                                                  │
                                                  ▼
                                         ┌─────────────┐
                                         │   Action   │
                                         │   Planner  │
                                         │ (Higher    │
                                         │   Trust)   │
                                         └─────────────┘
```

```python
class ContentTrustClassifier:
    """Classify content trust level"""
    
    TRUST_LEVELS = {
        "system_prompt": "trusted",
        "user_direct": "trusted", 
        "retrieved_memory": "medium_trust",
        "web_content": "untrusted",
        "ocr_output": "untrusted",
        "email_content": "untrusted",
        "uploaded_file": "untrusted"
    }
    
    def classify(self, source: str) -> str:
        return self.TRUST_LEVELS.get(source, "untrusted")
    
    def get_processing_pipeline(self, source: str) -> list[str]:
        """Get processing steps based on trust level"""
        
        trust = self.classify(source)
        
        if trust == "trusted":
            return ["parse"]
        elif trust == "medium_trust":
            return ["sanitize", "validate", "parse"]
        else:  # untrusted
            return ["sanitize", "detect_injection", "validate", "parse", "isolate"]
```

---

## 6. Rate Limiting (AI Abuse Prevention)

### 6.1 Token and Request Budgets

```python
class AIResourceLimiter:
    """Prevent abuse of AI resources"""
    
    LIMITS = {
        "requests_per_minute": {
            "free": 10,
            "basic": 60,
            "premium": 300
        },
        "tokens_per_day": {
            "free": 10000,
            "basic": 100000,
            "premium": 1000000
        },
        "expensive_workflows_per_hour": {
            "free": 2,
            "basic": 20,
            "premium": 100
        }
    }
    
    async def check_limits(
        self, 
        user_id: str, 
        tier: str,
        request: AIRequest
    ) -> LimitCheckResult:
        
        # Check request rate
        rate_key = f"rate:{user_id}:minute"
        rate = await self.redis.incr(rate_key)
        if rate > self.LIMITS["requests_per_minute"].get(tier, 10):
            return LimitCheckResult(allowed=False, reason="Rate limit exceeded")
        
        # Check token budget
        token_key = f"tokens:{user_id}:day"
        tokens = await self.redis.get(token_key)
        if tokens and int(tokens) > self.LIMITS["tokens_per_day"].get(tier, 10000):
            return LimitCheckResult(allowed=False, reason="Token budget exceeded")
        
        return LimitCheckResult(allowed=True)
```

---

## 7. Adversarial Testing

### 7.1 Test Categories

| Category | Tests | Frequency |
|----------|-------|-----------|
| Prompt Injection | Direct, indirect, context stealing | Weekly |
| Output Safety | Dangerous commands, PII leakage | Weekly |
| Denial of Service | Token exhaustion, loops | Monthly |
| Data Leakage | Training data extraction | Monthly |
| Tool Abuse | Unauthorized access, parameter injection | Weekly |

---

## 8. Monitoring

### 8.1 AI Security Metrics

```python
AI_SECURITY_METRICS = {
    # Injection attempts
    "prompt_injection_attempts_total": Counter,
    "prompt_injection_blocked_total": Counter,
    
    # Output safety
    "dangerous_output_blocked_total": Counter,
    "schema_validation_failures_total": Counter,
    
    # Tool gating
    "tool_deny_unauthorized_total": Counter,
    "tool_approval_requested_total": Counter,
    "tool_approval_denied_total": Counter,
    
    # Retrieval
    "restricted_memory_access_attempted_total": Counter,
    "untrusted_content_detected_total": Counter,
    
    # Resource abuse
    "rate_limit_exceeded_total": Counter,
    "token_budget_exceeded_total": Counter
}
```

---

## Summary

| Control | Implementation |
|---------|----------------|
| Prompt injection | Input sanitization, pattern detection |
| Output validation | Schema validation, dangerous pattern detection |
| Tool gating | Allowlist, permission check, approval flow |
| Retrieval safety | Access control, purpose matching |
| Model isolation | Trust levels, processing pipeline |
| Rate limiting | Per-user, per-tier limits |
| Adversarial testing | Weekly automated tests |

---

*Document owner: Security + ML Teams*  
*Version: 1.0*