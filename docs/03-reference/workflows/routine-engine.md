# Routine Engine

> **Status:** Authoritative
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## 1. Overview

The **Routine Engine** handles **recurring contextual assistant behavior** - not timed cron jobs, but intelligent behavior triggered by user context and activity.

**Examples:**
- Morning briefing (time + activity)
- Pre-meeting prep
- Commute mode
- Security check at night

---

## 2. Routine Definition

```typescript
interface Routine {
  id: UUID;
  userId: UUID;
  name: string;              // e.g., "Morning Briefing"
  description: string;
  
  // Triggers
  triggers: RoutineTrigger[];
  
  // Behavior definition
  behavior: RoutineBehavior;
  
  // State
  enabled: boolean;
  learnedFrom: string[];     // User feedback sources
  
  createdAt: timestamp;
  updatedAt: timestamp;
}

interface RoutineTrigger {
  type: 'time' | 'location' | 'activity' | 'event';
  condition: JSON;          // Flexible condition
  confidence: float;       // 0-1, how confident to trigger
}

interface RoutineBehavior {
  initialActions: MacroAction[];
  adaptive: boolean;        // Learns from user reactions
  learningRate: number;   // How fast adapts
}
```

---

## 3. Trigger Types

### 3.1 Time Trigger

```json
{
  "type": "time",
  "condition": {
    "start": "08:00",
    "end": "09:00",
    "weekdays": [1, 2, 3, 4, 5]
  },
  "confidence": 0.9
}
```

### 3.2 Location Trigger

```json
{
  "type": "location",
  "condition": {
    "geofence": "home",
    "enter": true           // vs exit
  },
  "confidence": 0.85
}
```

### 3.3 Activity Trigger

```json
{
  "type": "activity",
  "condition": {
    "activity": "driving",
    "duration_minutes": 10
  },
  "confidence": 0.8
}
```

### 3.4 Event Trigger

```json
{
  "type": "event",
  "condition": {
    "meeting_starts_in": 900,  // 15 minutes
    "focus_mode": true
  },
  "confidence": 0.95
}
```

---

## 4. Context Triggers

Routines can also trigger based on Butler's **internal context**:

| Context | Example Trigger |
|---------|-----------------|
| Task completed | When big task done, suggest break |
| Repeated failure | When tool fails 3x, suggest manual |
| Low confidence | When intent < 0.5, ask user |
| Memory gap | When user mentions new info |

---

## 5. Execution Flow

```
Time/Location/Activity detected
    ↓
Evaluate ALL enabled routines
    ↓
Calculate confidence for each
    ↓
If confidence >= threshold → trigger
    ↓
Build behavior from macro actions
    ↓
Execute with user context
    ↓
Push output to user
    ↓
Wait for feedback (if adaptive)
    ↓
Update learned parameters
```

---

## 6. Adaptive Behavior

### Learning Sources

1. **Implicit feedback** - User ignores, uses, or modifies routine output
2. **Explicit feedback** - User rates routine (thumbs up/down)
3. **Modification** - User edits routine in settings

### Adaptation Rules

```python
class RoutineLearner:
    def update(self, routine_id, feedback):
        if feedback == "ignored":
            # Decrease priority
            self.routine.confidence *= 0.9
        elif feedback == "used":
            # Increase priority
            self.routine.confidence *= 1.1
        elif feedback == "modified":
            # Learn from changes
            self._learn_patterns(feedback.changes)
```

---

## 7. Built-in Routines

| Routine | Trigger | Behavior |
|---------|----------|---------|
| Morning Briefing | 8-9am weekdays | Calendar + weather + tasks |
| Evening Wind Down | 6-7pm | Tasks review + tomorrow |
| Meeting Prep | 15min before | Notes + context |
| Commute Mode | Location=transit | Brief updates |
| Bedtime Check | 10pm | Security + tomorrow |
| Focus Mode | Calendar=deep work | Minimal interruption |

---

## 8. Routine vs Macro

| Aspect | Macro | Routine |
|--------|-------|----------|
| Execution time | <30s | Variable |
| Trigger | Explicit | Contextual |
| Adaptation | None | Learned |
| Approval | Often required | Usually auto |
| Complexity | Simple sequence | Contextual behavior |

---

## 9. Safety

- Routines always show enabled state
- User can disable any routine instantly
- Location triggers require explicit permission
- Activity detection is local-only by default

---

## 10. Storage

| Storage | Schema |
|---------|--------|
| PostgreSQL | Routine definitions |
| Redis | Active trigger state |
| Neo4j | Context relationships |
| Qdrant | Similar routine retrieval |

---

*Routine engine owner: Automation Team*
*Version: 4.0*