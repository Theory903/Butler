# Document Precedence

> **Status:** Authoritative
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## 1. Precedence Order

When documents conflict, resolve in this order (highest to lowest):

| Rank | Document | Examples |
|------|----------|---------|
| 1 | **Platform Constitution** | Service boundaries, non-negotiables |
| 2 | **System Design Rules** | RFC compliance, security rules |
| 3 | **Object Model** | Entity definitions |
| 4 | **Event Contract** | Event schema |
| 5 | **Request Envelope** | API schemas |
| 6 | **Core Docs (BRD→LLD)** | Business→Implementation |
| 7 | **Service Docs** | Individual service spec |
| 8 | **Reference Docs** | API, workflows, plugins |
| 9 | **Operations Docs** | Runbooks, deployment, security |
| 10 | **Development Docs** | Setup, build order |
| 11 | **Code** | Implementation |

---

## 2. Core Doc Hierarchy

Within 01-core/:

```
BRD → PRD → TRD → HLD → LLD
```

| Conflict | Resolution |
|----------|------------|
| BRD vs PRD | BRD wins (business intent) |
| PRD vs TRD | PRD wins (product requirements) |
| TRD vs HLD | TRD wins (technical decisions) |
| HLD vs LLD | HLD wins (architecture) |

---

## 3. Service Doc Hierarchy

Within 02-services/:

| Conflict | Resolution |
|----------|------------|
| Service vs HLD | HLD wins |
| Service vs LLD | LLD wins |
| Service vs Service | Platform Constitution wins |

---

## 4. Resolving Conflicts

### Step 1: Identify the Rank
Check which docs are in conflict.

### Step 2: Apply Higher Rank Wins
The document with higher precedence wins.

### Step 3: Document the Disagreement
If resolution is unclear, document in:
- Service doc: "Open Questions" section
- Core doc: Issue tracked in project

### Step 4: Escalate If Needed
If docs span different ranks:
- Technical → TRD owner
- Product → PRD owner
- Business → BRD owner

---

## 5. Exception Cases

### Security
All security docs supersede other operations docs in security matters.

### API Contracts
When API contracts conflict:
- Public API spec takes precedence over internal
- RFC compliance required

### Protocol Standards
When protocol conflicts:
- RFC standard takes precedence
- Document rationale if deviating

---

## 6. Metadata Required

Every doc MUST indicate:

| Field | Description |
|-------|-----------|
| Version | Doc version |
| Status | authoritative, draft, or production-required |
| Source of Truth Rank | 1-11 from above |
| Depends On | List of dependent docs |
| Supersedes | List of superseded docs |

---

*Precedence owner: Architecture Team*
*Version: 4.0*