# Request Envelope

> **Status:** Authoritative
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## 1. Envelope Schema

All API requests MUST use this envelope structure:

```typescript
interface ButlerRequest {
  // Actor identification
  actor: {
    userId: UUID;
    sessionId: UUID;
    deviceId?: string;
    channel: 'mobile' | 'web' | 'voice' | 'websocket';
  };
  
  // Security context
  security: {
    assurance: 'low' | 'medium' | 'high';
    tokenId?: UUID;
    proofOfPresence?: string;
  };
  
  // Request content
  content: {
    message: string;
    attachments?: Attachment[];
    context?: RequestContext;
  };
  
  // Tracing
  tracing: {
    traceId: UUID;
    spanId?: string;
    correlationId?: string;
  };
  
  // Metadata
  meta: {
    version: '1';
    timestamp: ISO8601;
    idempotencyKey?: string;
  };
}
```

---

## 2. Request Context

```typescript
interface RequestContext {
  // Session context
  sessionHistory?: string[];        // Last N message IDs
  activeTaskId?: UUID;
  
  // Location context
  location?: {
    latitude: number;
    longitude: number;
    accuracy?: number;
  };
  
  // Time context
  timezone?: string;
  localTime?: string;
  
  // Device context
  deviceState?: {
    batteryLevel?: number;
    orientation?: 'portrait' | 'landscape';
    connectivity?: 'online' | 'offline';
  };
  
  // User state
  userAvailability?: 'available' | 'busy' | 'do_not_disturb';
}
```

---

## 3. Response Envelope

```typescript
interface ButlerResponse {
  // Request reference
  requestRef: {
    traceId: UUID;
    messageId: UUID;
    timestamp: ISO8601;
  };
  
  // Status
  status: {
    code: 200 | 400 | 401 | 403 | 429 | 500 | 502 | 503;
    type: 'success' | 'error';
  };
  
  // Content
  content: {
    message: string;
    suggestions?: string[];
    attachments?: Attachment[];
  };
  
  // Execution state
  execution?: {
    taskId?: UUID;
    status: 'pending' | 'running' | 'completed' | 'failed';
    steps?: TaskStep[];
    approvalRequired?: boolean;
  };
  
  // Memory updates
  memory?: {
    stored: number;
    updated: number;
  };
  
  // Latency
  latency: {
    total: number;           // ms
    breakdown?: {
      intent: number;
      memory: number;
      generation: number;
      execution: number;
    };
  };
}
```

---

## 4. Error Envelope (RFC 9457)

```typescript
interface ProblemDetail {
  type: string;              // URI reference
  title: string;
  status: number;
  detail: string;
  instance: string;         // HTTP method + path
  traceId?: string;
  errors?: ValidationError[];
  
  // Butler-specific
  recovery?: {
    action: 'retry' | 'reauth' | 'approve' | 'contact_support';
    retryAfter?: number;
  };
}

interface ValidationError {
  field: string;
  message: string;
  code: string;
}
```

---

## 5. Idempotency

Idempotency key format:

```
idempotency-key: "{actor_id}:{method}:{path}:{hash(content)}"
```

Example:
```
Idempotency-Key: "usr_abc:POST:/api/v1/chat:a1b2c3d4"
```

Requirements:
- Safe to retry on 5xx
- Safe to retry on network timeout (no response)
- NOT safe to retry on 200-299 (already processed)
- Store for 24 hours minimum

---

## 6. Attachments

```typescript
interface Attachment {
  id: UUID;
  type: 'image' | 'audio' | 'video' | 'document';
  mimeType: string;
  size: number;             // bytes
  url?: string;            // Pre-signed S3 URL
  content?: string;        // Base64 inline (max 1MB)
  thumbnail?: string;     // Base64 thumbnail
  metadata?: {
    width?: number;
    height?: number;
    duration?: number;
    transcription?: string;
  };
}
```

---

## 7. Version Migration

When breaking changes required:

1. Add new version alongside old
2. Deprecate old after 2 releases
3. Support both for migration window

```http
Accept: application/vnd.butler.v2+json
```

---

*Request envelope owner: Architecture Team*
*Version: 4.0*