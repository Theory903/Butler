# Object Model

> **Status:** Authoritative
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## 1. Core Entities

### 1.1 User

```typescript
interface User {
  id: UUID;                    // Primary key
  email: string;              // Unique, validated
  phone?: string;            // E.164 format
  displayName: string;
  createdAt: timestamp;
  updatedAt: timestamp;
  status: 'active' | 'suspended' | 'deleted';
  preferences: JSON;         // Encrypted
  metadata: JSON;
}
```

### 1.2 Session

```typescript
interface Session {
  id: UUID;
  userId: UUID;             // FK -> User
  deviceId: string;
  channel: 'mobile' | 'web' | 'voice' | 'websocket';
  startedAt: timestamp;
  endedAt?: timestamp;
  context: {
    location?: GeoJSON;
    timezone: string;
    deviceInfo: JSON;
  };
  assurance: 'low' | 'medium' | 'high';
}
```

### 1.3 Message

```typescript
interface Message {
  id: UUID;
  sessionId: UUID;          // FK -> Session
  role: 'user' | 'assistant' | 'system';
  content: string;
  intent?: string;
  confidence?: float;
  tokensUsed?: number;
  latencyMs?: number;
  createdAt: timestamp;
}
```

### 1.4 Task

```typescript
interface Task {
  id: UUID;
  sessionId: UUID;
  userId: UUID;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  intent: string;
  plan?: TaskPlan;
  result?: JSON;
  error?: string;
  safetyClass: SafetyClass;
  approvalRequired: boolean;
  approvedAt?: timestamp;
  createdAt: timestamp;
  completedAt?: timestamp;
}

interface TaskPlan {
  steps: TaskStep[];
  dag: DAG;
}

interface TaskStep {
  id: string;
  tool: string;
  params: JSON;
  dependsOn: string[];
  status: 'pending' | 'running' | 'completed' | 'failed';
  result?: JSON;
}
```

### 1.5 Memory

```typescript
interface Memory {
  id: UUID;
  userId: UUID;
  type: 'preference' | 'fact' | 'relationship' | 'conversation' | 'routine';
  content: string;
  importance: 1-10;
  embedding?: Vector;
  source?: string;
  createdAt: timestamp;
  updatedAt: timestamp;
}
```

### 1.6 Macro

```typescript
interface Macro {
  id: UUID;
  userId: UUID;
  name: string;
  description: string;
  trigger: string;           // Pattern or schedule
  actions: MacroAction[];
  enabled: boolean;
  runCount: number;
  lastRunAt?: timestamp;
  createdAt: timestamp;
}

interface MacroAction {
  order: number;
  tool: string;
  params: JSON;
}
```

### 1.7 Routine

```typescript
interface Routine {
  id: UUID;
  userId: UUID;
  name: string;
  description: string;
  schedule?: {
    type: 'time' | 'location' | 'event';
    pattern: string;
  };
  contextTriggers: JSON;
  behavior: RoutineBehavior;
  enabled: boolean;
  createdAt: timestamp;
}

interface RoutineBehavior {
  initialActions: MacroAction[];
  adaptive: boolean;
  learning: boolean;
}
```

### 1.8 Workflow

```typescript
interface Workflow {
  id: UUID;
  userId: UUID;
  name: string;
  description: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  config: WorkflowConfig;
  status: 'draft' | 'active' | 'paused';
  runCount: number;
  createdAt: timestamp;
}

interface WorkflowNode {
  id: string;
  type: 'trigger' | 'action' | 'condition' | 'delay';
  config: JSON;
}

interface WorkflowConfig {
  timeout: number;           // ms
  retryPolicy?: RetryPolicy;
  approvalAtStep?: string;
}
```

---

## 2. Safety Classes

```typescript
enum SafetyClass {
  SAFE_AUTO = 'safe_auto',      // Execute without approval
  CONFIRM = 'confirm',        // Require approval
  RESTRICTED = 'restricted', // Elevated approval
  FORBIDDEN = 'forbidden'    // Never execute
}
```

---

## 3. Session Assurance Levels

| Level | Requires | Token Lifetime |
|-------|----------|---------------|
| low | Password | 7 days |
| medium | 2FA | 24 hours |
| high | Biometric | 1 hour |

---

## 4. Device State

```typescript
interface Device {
  id: UUID;
  userId: UUID;
  type: 'mobile' | 'web' | 'voice' | 'wearable' | 'desktop';
  platform: string;
  pushToken?: string;
  lastSeenAt: timestamp;
  capabilities: string[];
}
```

---

*Object model owner: Architecture Team*
*Version: 4.0*