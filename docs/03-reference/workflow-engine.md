# Butler Workflow Engine Specification

> **For:** Engineering  
> **Status:** Authoritative Draft  
> **Version:** 2.0

---

## 1. Execution Model Overview

Butler implements **three execution layers**, not one generic DAG engine:

| Class | Purpose | Latency Target | Example |
|-------|---------|---------------|----------|
| **Macro** | Repeated short action template | 50–300ms | "send my daily standup" |
| **Routine** | Recurring contextual behavior | 100ms–seconds | Morning briefing |
| **Workflow** | Durable multi-step process | seconds–days | Approval-gated travel planner |

### Core Rule

> Do not build a workflow for every repeated task.
> 
> Promote repeated user behavior into **macro**, **routine**, or **durable workflow**
> depending on complexity and durability needs.

---

## 2. Macro Specification

A macro is a **compiled, reusable execution template** for repeated short actions.

### 2.1 Macro Schema

```yaml
macro:
  id: uuid
  name: string
  intent_family: string
  description: string
  trigger_hints:
    - manual
    - suggested
    - shortcut
    - voice
  slots:
    - name: location
      type: string
      required: false
      default_source: memory.preference.default_location
  plan_template:
    tool_candidates: [weather.get_current, calendar.get_today]
    response_template: "Weather: {weather}; Calendar: {calendar}"
  safety_class: safe_auto | confirm | restricted
  cache_policy:
    candidate_cache_ttl_sec: 300
  version: integer
  status: active | paused
  created_at: timestamp
  updated_at: timestamp
```

### 2.2 Why Macros?

A macro skips:
- Repeated full planning
- Repeated candidate search explosion
- Repeated graph authoring for trivial actions

```python
class MacroRuntime:
    async def run(self, macro_id: str, request_ctx: RequestContext) -> MacroResult:
        macro = await self.repo.get_macro(macro_id)
        slots = await self.slot_resolver.resolve(macro.slots, request_ctx)
        candidates = await self.candidate_cache.get_or_compute(macro, slots)
        checked = await self.policy.check_macro(macro, request_ctx, slots)
        result = await self.tool_executor.run_compiled(candidates, slots, checked)
        return self.responder.render(macro.plan_template, result)
```

### 2.3 Macro Example: "Morning Weather"

```yaml
name: "Check Weather"
intent_family: "weather.check"
trigger_hints: [manual, voice]
slots:
  - name: location
    type: string
    required: false
    default_source: memory.preference.home_location
plan_template:
  tool_candidates: [weather.get_current]
  response_template: "It's {temperature}° and {condition} in {location}"
safety_class: safe_auto
cache_policy:
  candidate_cache_ttl_sec: 300
```

---

## 3. Routine Specification

A routine is a **recurring, context-aware macro set** with durable state.

### 3.1 Routine Schema

```yaml
routine:
  id: uuid
  name: string
  owner_account_id: uuid
  description: string
  schedule:
    type: cron | window | contextual | event
    cron: "0 7 * * *"          # if type: cron
    window:                    # if type: window
      start: "07:00"
      end: "09:00"
    rule: "first_unlock_after(07:00, timezone=user)"  # if type: contextual
  conditions:
    - device_capability: mobile
    - quiet_hours_excluded: true
    - battery_threshold: 20
  steps:
    - macro_ref: macro_weather_brief
      on_failure: skip
    - macro_ref: macro_calendar_brief
      on_failure: skip
    - macro_ref: macro_news_brief
      on_failure: skip
  adaptation:
    can_skip_if_no_change: true
    can_delay_if_user_sleeping: true
    skip_conditions:
      - user_on_vacation: true
      - calendar.event: "out_of_office"
  delivery:
    channel: push | voice | mobile | watch
    priority: high | normal | low
  safety_class: safe_auto | confirm
  status: active | paused
  last_run_at: timestamp
  created_at: timestamp
  updated_at: timestamp
```

### 3.2 Why Routines?

A routine is **not just cron**. It is:
- Schedule + context + memory + policy + delivery
- Device-aware
- User-presence aware
- Interruption/resume capable
- Policy-classed

### 3.3 Routine Runtime

```python
class RoutineRuntime:
    async def tick(self, routine_id: str, now: datetime):
        routine = await self.repo.get_routine(routine_id)
        
        # Check conditions
        if not await self.condition_engine.should_run(routine, now):
            return RoutineTickResult.skipped(reason="conditions_not_met")
        
        # Check adaptation rules
        if routine.adaptation.can_skip_if_no_change:
            if not await self.has_new_content(routine):
                return RoutineTickResult.skipped(reason="no_change")
        
        # Execute steps
        outputs = []
        for step in routine.steps:
            try:
                result = await self.macro_runtime.run(step.macro_ref, routine.context())
                outputs.append(result)
            except Exception as e:
                if step.on_failure == "skip":
                    continue
                raise
        
        # Deliver
        return await self.delivery.dispatch(routine, outputs)
```

### 3.4 Schedule Types

```yaml
# Cron-based
schedule:
  type: cron
  cron: "0 7 * * *"

# Time window
schedule:
  type: window
  window:
    start: "07:00"
    end: "09:00"

# Contextual trigger
schedule:
  type: contextual
  rule: "first_unlock_after(07:00, timezone=user)"

# Event trigger
schedule:
  type: event
  event: "calendar.first_meeting_in_30m"
```

---

## 4. Durable Workflow Specification

A workflow is for **durability and coordination**, not repeated trivial actions.

### 4.1 Workflow Schema

```yaml
workflow:
  id: uuid
  name: string
  description: string
  version: integer
  trigger:
    type: manual | event | routine | api
  graph:
    nodes: []
    edges: []
  execution_policy:
    timeout_sec: 86400
    retry_policy:
      max_attempts: 3
      backoff_multiplier: 2
    continue_as_new_threshold: 1000_events
  compensation:
    enabled: true
  approval_policy:
    required_on_nodes: []
  safety_class: confirm | restricted
  status: draft | active
  created_at: timestamp
  updated_at: timestamp
```

### 4.2 Butler Node Types

| Node Type | Purpose |
|----------|---------|
| `tool_call` | Execute a verified tool |
| `macro_call` | Run compiled repeated action |
| `memory_read` | Retrieve context |
| `memory_write` | Persist structured memory |
| `policy_gate` | Evaluate safety/approval |
| `approval_wait` | Pause for user/admin decision |
| `transform` | Template/render/normalize |
| `branch` | Route by condition |
| `delay_until` | Resumable wait |
| `emit_event` | Publish typed event |
| `subworkflow` | Spawn child durable workflow |
| `delivery` | Send result to channel |

### 4.3 Removed: Generic HTTP Node

> **Do NOT expose raw HTTP nodes as first-class public primitives.**
> 
> External HTTP calls should happen through:
> - `tool_call` (via Tools service)
> - Provider adapter
> - Communication/Search/Device service boundary
>
> If you keep raw HTTP nodes everywhere, engineers will bypass the Tools service.

### 4.4 Durable Workflow Runtime

```python
class DurableWorkflowRuntime:
    async def advance(self, execution_id: str):
        execution = await self.execution_store.load(execution_id)
        graph = await self.graph_store.load(execution.workflow_id)
        
        ready = self.scheduler.ready_nodes(graph, execution.state)
        for node in ready:
            await self.node_runner.run(node, execution)
        
        await self.execution_store.save(execution)
```

### 4.5 Durable Execution Rules

- Execution state in **PostgreSQL** (source of truth)
- Append-only execution event trail
- Approval pause persists as explicit state
- Timers are **resumable**, not sleep calls
- Long-lived runs checkpoint with continue-as-new style boundaries
- Subworkflow fanout only where throughput/composability justify it

---

## 5. Repetition Promotion Pipeline

When Butler sees repeated executions of similar actions, it **promotes** them.

### 5.1 Promotion Levels

```
1. ad hoc execution
2. suggested macro
3. saved macro
4. routine candidate
5. durable workflow (only if needed)
```

### 5.2 Promotion Logic

```python
class RepetitionPromoter:
    async def observe(self, execution: ExecutionRecord):
        cluster = await self.clusterer.assign(execution)
        stats = await self.stats.update(cluster, execution)
        
        # Suggest promotion
        if stats.repeat_count >= 5 and stats.structure_stability >= 0.8:
            return PromotionSuggestion(
                type="macro" if stats.duration_ms < 1000 else "routine",
                cluster_id=cluster.id
            )
```

### 5.3 Promotion Inputs

- Repeated tool sequence
- Repeated time window
- Repeated recipient or device context
- Repeated approval-free execution
- Low variance in plan structure
- High success rate

### 5.4 Example

User manually does:
- check weather → check calendar → summarize day

for 10 mornings.

Butler detects:
- Stable sequence
- Stable time window
- Stable preferred channel
- Stable slot sources

Then proposes:

> "I can turn this into your morning routine."

Not:
> Create 5 nodes, connect 4 edges, ask human to graph their own life.

---

## 6. Runtime Interaction Model

Durable executions should be **interactive**.

### 6.1 Interaction Channels

| Channel | Purpose | Butler Example |
|---------|---------|---------------|
| **Signal** | Append external input to running execution | User approves action |
| **Query** | Inspect state without mutation | "Where is this task?" |
| **Update** | Request mutation with validation | User changes destination |

### 6.2 API Contracts

```yaml
# Macro APIs
POST   /macros                      # Create macro
GET    /macros                      # List macros
GET    /macros/{macro_id}            # Get macro
POST   /macros/{macro_id}/run        # Run macro
POST   /macros/{macro_id}/promote-to-routine

# Routine APIs
POST   /routines                     # Create routine
PATCH  /routines/{routine_id}       # Update routine
POST   /routines/{routine_id}/pause
POST   /routines/{routine_id}/resume
GET    /routines/{routine_id}/history

# Workflow APIs
POST   /workflows                    # Create workflow
POST   /workflows/{workflow_id}/start
GET    /executions/{execution_id}
POST   /executions/{execution_id}/signal
POST   /executions/{execution_id}/update
POST   /executions/{execution_id}/cancel
```

---

## 7. Observability

Every macro/routine/workflow run emits:

```yaml
execution.class: macro | routine | workflow
execution.id: uuid
workflow.id: uuid        # if workflow
routine.id: uuid          # if routine
macro.id: uuid           # if macro
step.id: uuid
step.type: string
resume.count: integer
approval.wait_ms: integer
compensation.count: integer
```

> Use **OpenTelemetry semantic conventions** for base trace/log/metric naming.

---

## 8. Queue and Wake-up Model

> **Do NOT use Redis Pub/Sub for durable work.**
> 
> Use:
> - **PostgreSQL** = source of truth
> - **Redis Streams** = wakeups, async jobs, fanout
> - Workers **ack** work only after state is committed

---

## 9. Example Redesign: "Morning Briefing"

### Old Way (v1.0)

One giant workflow graph for a daily repeated task.

### New Way (v2.0)

**Macros:**
- `macro.weather_brief`
- `macro.calendar_brief`
- `macro.news_brief`

**Routine:**
```yaml
name: "Morning Briefing"
schedule:
  type: contextual
  rule: "first_unlock_after(07:00, timezone=user)"
conditions:
  - quiet_hours_excluded: true
steps:
  - macro_ref: macro_weather_brief
  - macro_ref: macro_calendar_brief
  - macro_ref: macro_news_brief
adaptation:
  can_skip_if_no_change: true
  can_delay_if_user_sleeping: true
delivery:
  channel: mobile_push
  priority: normal
status: active
```

**Durable workflow only if needed:**

If user says:
> "If severe weather, reschedule morning walk and notify me"

Then escalate into workflow for branching, approvals, and compensations.

---

## 10. Final Rules

Butler should **NOT** be:
> "A DAG engine that forces all repeated life behavior into node-edge graphs."

Butler should **be**:
- **Macro engine** for repeated short actions
- **Routine engine** for recurring assistant behavior
- **Durable workflow engine** for long-running coordinated processes

That makes it:
- Faster
- More personal
- Easier to author
- Easier to learn from
- Less repetitive

---

*Document owner: Workflow Team*  
*Last updated: 2026-04-18*  
*Version: 2.0 (Oracle-Grade)*