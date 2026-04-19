# Durable Workflow Engine

> **Status:** Authoritative
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## 1. Overview

The **Durable Workflow Engine** handles **long-running, approval-aware, resumable tasks** - full workflows with DAGs, compensation, and checkpointing.

**Not:** Quick macros, simple sequences.

**Examples:**
- Trip planning with approval gates
- Account setup flows
- Multi-app form completion
- Cross-device automations with auditability

---

## 2. Workflow Definition

```typescript
interface Workflow {
  id: UUID;
  userId: UUID;
  name: string;
  description: string;
  
  // DAG structure
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  
  // Configuration
  config: WorkflowConfig;
  
  // State
  status: 'draft' | 'active' | 'paused' | 'completed' | 'failed';
  
  // Stats
  runCount: number;
  avgDuration: number;
  
  createdAt: timestamp;
  updatedAt: timestamp;
}

interface WorkflowNode {
  id: string;
  type: 'trigger' | 'action' | 'condition' | 'delay' | 'approval' | 'compensation';
  config: NodeConfig;
}

interface WorkflowConfig {
  timeout: number;           // Max execution time
  retryPolicy?: RetryPolicy;
  approvalAtStep?: string;   // Node ID requiring approval
  checkpointAt?: string[];   // Node IDs for resume
}
```

---

## 3. Node Types

### 3.1 Trigger Node

```json
{
  "type": "trigger",
  "config": {
    "event": "user_command",
    "pattern": "plan.*trip.*"
  }
}
```

### 3.2 Action Node

```json
{
  "type": "action",
  "config": {
    "tool": "search_flights",
    "params": {
      "from": "{{inputs.from}}",
      "to": "{{inputs.to}}",
      "date": "{{inputs.date}}"
    }
  }
}
```

### 3.3 Condition Node

```json
{
  "type": "condition",
  "config": {
    "expression": "{{steps.search.price}} < {{inputs.budget}}",
    "trueTarget": "book_flight",
    "falseTarget": "notify_user"
  }
}
```

### 3.4 Delay Node

```json
{
  "type": "delay",
  "config": {
    "duration": "{{inputs.approval_wait}}"
  }
}
```

### 3.5 Approval Node

```json
{
  "type": "approval",
  "config": {
    "prompt": "Book flight for ${{steps.search.price}}?",
    "safetyClass": "confirm",
    "timeout": 300
  }
}
```

### 3.6 Compensation Node

```json
{
  "type": "compensation",
  "config": {
    "onFailure": "cancel_flight",
    "target": "search_flight"
  }
}
```

---

## 4. Temporal Concepts

Adapted from Temporal.io:

| Concept | Butler Implementation |
|---------|-------------------|
| **Signals** | External input to running workflow |
| **Queries** | Read workflow state |
| **Updates** | Modify workflow state |
| **Continue-as-new** | Long history truncation |
| **Activities** | Individual tool executions |

### Signals

```python
# Send signal to running workflow
await client.signal_workflow(
    workflow_id="wf_123",
    signal="update_booking",
    args={"new_date": "2026-05-15"}
)
```

### Queries

```python
# Query current state
state = await client.query_workflow(
    workflow_id="wf_123",
    query="current_step"
)
```

---

## 5. Execution Flow

```
User Input: "Plan a trip to NYC"
    ↓
Create workflow (DAG)
    ↓
Execute step by step
    ↓
If approval node → Pause + Notify
    ↓
User approves/denies
    ↓
Resume or Cancel
    ↓
... continue ...
    ↓
Checkpoint at each node
    ↓
Completion + Memory update
```

---

## 6. Resume on Failure

### Checkpoints

Every workflow marks checkpoints:

```python
@workflow
async def plan_trip():
    search = await execute_node("search_flights")
    await create_checkpoint("search_flights", search)
    
    if approval_needed:
        await pause_until_approval()
    
    book = await execute_node("book_flight")
    await create_checkpoint("book_flight", book)
```

### Resume

```python
# On service restart or failure
await workflow_resume(
    workflow_id="wf_123",
    from_checkpoint="search_flights"
)
```

---

## 7. Compensation (Rollback)

On failure, execute compensation nodes:

```
Workflow: Book Flight
    ↓
Step 1: Search Flight (OK)
    ↓
Step 2: Book Hotel (FAILED)
    ↓
Compensation: Cancel Hotel (run on failure)
    ↓
Compensation: Cancel Flight (if configured)
```

---

## 8. Approval Gates

### Safety Classes at Nodes

| Class | Auto-Proceed | Requires Approval |
|------|--------------|------------------|
| safe_auto | Yes | No |
| confirm | No | Yes |
| restricted | No | Elevated |

### Approval Timeout

- Default: 5 minutes
- Configurable: 1min - 24h
- On timeout: Fail or notify

---

## 9. Limits

| Limit | Value |
|-------|-------|
| Max nodes | 50 |
| Max depth | 10 |
| Max execution | 24 hours |
| Checkpoints | Per node |
| Retries | 3 default |

---

## 10. Storage

| Storage | Schema |
|---------|--------|
| PostgreSQL | Workflow definitions |
| PostgreSQL | Workflow state (checkpoints) |
| Redis Streams | Active execution queue |

---

## 11. Analytics

Track:

```json
{
  "workflowId": "wf_abc",
  "runId": "run_xyz",
  "status": "completed",
  "totalDuration": "45m",
  "nodeExecutions": [
    {"node": "search", "duration": "2s", "status": "completed"},
    {"node": "approval", "duration": "5m", "status": "completed"},
    {"node": "book", "duration": "30s", "status": "completed"}
  ]
}
```

---

*Durable workflow owner: Automation Team*
*Version: 4.0*