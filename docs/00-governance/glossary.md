# Glossary

> **Status:** Authoritative
> **Version:** 4.0
> **Last Updated:** 2026-04-18

---

## A

**Approval Gate:** A checkpoint in task execution requiring explicit user confirmation before proceeding with a high-safety-class action.

**Assurance Level:** The confidence level in user identity, determined by authentication factors. Levels: low (password), medium (2FA), high (biometric).

---

## B

**Butler Runtime:** The core AI system that unifies conversation, memory, action, routines, devices, and approvals.

---

## C

**Circuit Breaker:** A pattern that prevents cascading failures by failing fast when a downstream service exceeds error threshold.

**Confidence Score:** A float (0-1) indicating certainty of intent classification or response generation.

---

## D

**DAG (Directed Acyclic Graph):** A task plan structure where nodes are steps and edges are dependencies.

**Durable Execution:** Task execution that survives restarts, approval pauses, and delays. Uses resume, not restart.

---

## E

**Event Contract:** The standardized schema for all internal Butler events (user events, intent events, execution events, memory events).

---

## F

**Four-State Health:** The health model: STARTING → HEALTHY → DEGRADED → UNHEALTHY.

---

## G

**Gateway:** The HTTP entry point service. MUST never call Memory directly.

---

## I

**Idempotency:** Property where repeated execution produces same result. Required for all side-effect endpoints.

---

## J

**JWKS (JSON Web Key Set):** The public key set for JWT validation. MUST be served at `/.well-known/jwks`.

---

## M

**Macro:** A fast, repeatable action script. Example: "send daily standup", "summarize calendar".

**Memory (Service):** The service responsible for storing and retrieving user context. NEVER called directly from Gateway.

**ML (Service):** The service responsible for embeddings, ranking, and prediction signals.

---

## O

**Orchestrator:** The decision-making service. Routes requests to appropriate services, manages task lifecycle.

---

## P

**Platform Constitution:** The governing document defining Butler's thesis, 18 services, and non-negotiable boundaries.

**Problem Details (RFC 9457):** The standard error format. All errors MUST use this format.

---

## R

**RAG (Retrieval Augmented Generation):** Technique using retrieved context to enhance LLM generation.

**Refresh Token Rotation:** Pattern where each refresh request issues a new token and invalidates the old one.

---

## S

**Safety Class:** Classification determining approval requirements:
- `safe_auto` - Execute without approval
- `confirm` - Require approval
- `restricted` - Elevated approval
- `forbidden` - Never execute

**Session Assurance:** See Assurance Level.

**System Design Rules:** The authoritative technical standards document.

---

## T

**Temporal Concepts:** Durable execution concepts (signals, queries, updates, continue-as-new) adapted from Temporal.io.

---

## U

**User Session:** The authenticated context between user and Butler. Includes device, channel, and assurance level.

---

## W

**Workflow (Durable):** A long-running, multi-step task with approval gates, compensation, and resumability.

---

*Glossary owner: Architecture Team*
*Version: 4.0*