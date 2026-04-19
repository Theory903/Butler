# Draft: Butler MVP 2-Day Alpha Backend

## Requirements (confirmed)
- Alpha backend only
- Use `/Users/abhishekjha/CODE/Butler/docs` as source of truth
- Make a work plan for completing MVP in 2 days
- Use subagents heavily
- Ralph-loop compatible execution guidance
- Keep design KISS and SOLID
- Also produce a Hermes → Butler reference/cheat-sheet that looks beyond MVP toward the full service architecture
- The full-services reference should optimize for execution order, architecture map, and production hardening together
- Primary audience for the full strategic reference: future multi-agent execution system
- The full strategic reference should be very explicit: service-by-service mapping, dependencies, adapted-copy guidance, sequencing, risks, and verification expectations

## Technical Decisions
- Runtime shape: modular monolith first, preserve extraction boundaries
- MVP scope: Gateway, Auth, Orchestrator, Memory, Tools
- Contracts should follow docs over existing boilerplate code
- First golden flow: login -> chat -> history
- For the broader Butler strategy, use Hermes directly where it already has solid implementations, and design/implement Butler-native pieces where Hermes does not cover the requirement
- In the strategic reference, Hermes-backed Butler areas should default to **adapted copy** rather than direct lift or reference-only
- The full strategic reference should live in a separate draft document, not be folded into the MVP planning draft

## Research Findings
- Oracle: modular monolith first is safest, extract later
- FastAPI patterns: thin routes, dependency injection, service/domain separation, tests first
- Docs: `docs/product/mvp-services.md` defines MVP as 5 services only
- Docs: `docs/dev/build-order.md` defines 9-hour first working sequence
- Docs: `docs/system/first-flow.md` defines login/chat/history golden path
- Metis: lock scope, disclose assumptions, make acceptance criteria executable

## Scope Boundaries
- INCLUDE: alpha backend MVP launch path and backend runtime/test work
- INCLUDE: future-safe reference notes for Butler's full service architecture, as planning guidance only
- EXCLUDE: full 16/17-service production completeness
- EXCLUDE: frontend polish, mobile/web product completion
- EXCLUDE: post-MVP services unless needed as thin placeholders only

## Open Questions
- None for the strategic reference direction; ready for understanding lock confirmation
