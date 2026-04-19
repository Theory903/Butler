# Agent System Documentation

**Purpose:** How Butler thinks, decides, and acts

---

## OVERVIEW

Two core documents for agent behavior.

---

## WHERE TO LOOK

| Document | Purpose |
|----------|---------|
| agent-loop.md | How Butler processes requests |
| decision-tree.md | Clear decision rules for Butler |

---

## KEY CONCEPTS

- **Intent Classification**: Route user requests to correct handlers
- **Context Building**: Gather needed info before acting
- **Planning**: Create DAG-based execution plan
- **Execution**: Run plan with tool gating
- **Feedback Loop**: Learn from outcomes

---

## NOTES

- All decisions traced via context builder
- Tool execution sandboxed
- Prompt injection defense via input sanitization