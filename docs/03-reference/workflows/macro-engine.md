# Macro Engine

> **Status:** Authoritative
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## 1. Overview

The **Macro Engine** handles **fast, repeatable actions** - quick automation scripts that execute in seconds.

**Not:** Complex workflows, DAG editors, or approval gates.

**Examples:**
- "Send daily standup message"
- "Summarize my calendar"
- "Check flight status"
- "Text mom I'll be late"

---

## 2. Macro Definition

```typescript
interface Macro {
  id: UUID;
  userId: UUID;
  name: string;              // e.g., "Daily Standup"
  description: string;
  trigger: MacroTrigger;
  actions: MacroAction[];
  enabled: boolean;
  
  // Stats
  runCount: number;
  lastRunAt?: timestamp;
  createdAt: timestamp;
  updatedAt: timestamp;
}

interface MacroTrigger {
  type: 'text_pattern' | 'schedule' | 'manual';
  pattern?: string;         // e.g., "daily standup"
  schedule?: string;         // Cron expression
}

interface MacroAction {
  order: number;
  tool: string;             // Tool name from registry
  params: JSON;
}
```

---

## 3. Trigger Types

### 3.1 Text Pattern

```json
{
  "type": "text_pattern",
  "pattern": ".*daily standup.*"
}
```

Triggers when user message matches regex.

### 3.2 Schedule

```json
{
  "type": "schedule",
  "schedule": "0 9 * * 1-5"
}
```

Cron: Every weekday at 9 AM.

### 3.3 Manual

```json
{
  "type": "manual"
}
```

User triggers via quick action.

---

## 4. Execution Flow

```
User Input: "send daily standup"
    ↓
Intent Engine classifies
    ↓
Matches Macro trigger
    ↓
Load Macro actions
    ↓
Parallel execution (respected ordering)
    ↓
Tool execution
    ↓
Result verification
    ↓
Memory store (auto-learn)
    ↓
Push notification (if async)
```

---

## 5. Safety Classification

| Safety Class | Required Action |
|--------------|-----------------|
| safe_auto | Execute immediately |
| confirm | Pre-approval required |
| restricted | Not allowed for macros |
| forbidden | Blocked |

Macros default to `safe_auto` or `confirm`.

---

## 6. Creation via Natural Language

### Creation Flow

```
User: "Create a macro to send standup to the team every morning at 9am"
    ↓
Butler parses intent
    ↓
Butler extracts: name="Daily Standup", schedule="0 9 * * 1-5", action=send_message
    ↓
User confirms/edits in modal
    ↓
Macro created
```

### NL Examples

| User Input | Parsed Macro |
|------------|-------------|
| "Remind me of daily standup" | Schedule trigger, reminder tool |
| "Text mom when I'm running late" | Text pattern, send_sms |
| "Summarize my calendar every morning" | Schedule trigger, calendar tool |

---

## 7. Built-in Macros

| Macro | Trigger | Actions |
|-------|----------|---------|
| Morning Briefing | 8am daily | Calendar + weather + tasks |
| End of Day | 6pm daily | Tasks review + tomorrow preview |
| Meeting Prep | 15min before meeting | Calendar + notes |

---

## 8. Storage

| Storage | Schema |
|---------|--------|
| PostgreSQL | Macro definitions |
| Redis | Active run state |
| Neo4j | Macro relationships |

---

## 9. Logging

All macro executions log:

```json
{
  "eventType": "macro.executed",
  "macroId": "mac_abc",
  "userId": "usr_xyz",
  "trigger": "text_pattern",
  "actionsRun": 3,
  "success": true,
  "duration": "1.2s"
}
```

---

## 10. Limits

| Limit | Value |
|-------|-------|
| Max macros per user | 50 |
| Max actions per macro | 10 |
| Max execution time | 30s |
| Max parallel tools | 5 |

---

*Macro engine owner: Automation Team*
*Version: 4.0*