# BIS v2 Production Architecture

This document defines the production-grade Butler Intelligence System (BIS) v2 architecture: a multi-tenant, scalable, cost-efficient AI system with strict control over prompts, context, tools, execution, and end-to-end encryption for user data privacy.

## System Identity

BIS v2 is a governed cognitive organism with strict execution lanes, bounded deliberation, domain-specialized agents, and zero hardcoding. Every request falls to the cheapest capable execution lane via "Computational Gravity."

## Core Architecture Law

**Computational Gravity**: Every request escalates only when provably necessary.

- Complexity 1/2 → DETERMINISTIC_TOOL or LLM_ANSWER (nano tier)
- Complexity 3 → LLM_WITH_TOOLS with ReAct (mini tier)
- Complexity 4 → DOMAIN_CREW with Tree/Graph reasoning (mid tier)
- Complexity 5 → CREW_ASYNC with deep research (high tier)

## Core Principles (Mandatory)

1. **No Hardcoding Anywhere**
   - No hardcoded prompts, models, tools, thresholds, or configs
   - Everything must be configurable and injected at runtime

2. **Domain-First Architecture**
   - Business logic in domain/
   - Orchestration in services/
   - Infrastructure isolated
   - API layer contains zero business logic

3. **Frameworks at the Edge**
   - Domain must NOT depend on FastAPI, DB, or external services
   - All infrastructure enters through explicit interfaces

4. **Strict Dependency Direction**
   - api → services → domain
   - infrastructure → domain
   - NEVER reverse

5. **Agents Are NOT General-Purpose**
   - Must be domain-specialized
   - Must have strict tool scope
   - Must have fixed responsibilities

---

# BIS v2 — Personal Intelligence Operating System

## Complete Technical Architecture: Birth to Death, 0 → 100%

---

### PART 0 — WHAT THIS SYSTEM IS

BIS v2 is not a chatbot. It is a personal intelligence operating system that manages every dimension of a human life from birth records to end-of-life planning. It knows your finances, your health, your relationships, your career, your projects, your memories, and your mental state. It reasons across all of them without ever mixing raw data between domains.

The system is built on one law: every domain owns its data absolutely, communicates only through approved bridges, and the human is always the final authority.

It covers:

**Finance** — every rupee, every debt, every investment, every goal from your first pocket money to your retirement drawdown.

**Health** — every diagnosis, every medication, every lab result, every mood score, every therapy session, every fitness entry from birth records to end-of-life care.

**Projects** — every task, every milestone, every decision, every codebase, every research paper, every learning goal, completely isolated from personal data.

**Social Graph** — every person who matters to you, your history with them, their important dates, your relationship health, your family structure.

**History Graph** — the long-term memory of your entire life, every significant event across every domain, chains showing how one life event caused another, memories about yourself and memories about others clearly attributed.

**Digital Twin** — a live computed model of who you are right now, built from summaries of all domains, powering every AI agent that works for you.

**Study, Research, Work, Code, Ideate, Brainstorm, Learn** — all handled through the Project and Knowledge domains with specialized agents for every intellectual activity.

---

### PART 1 — THE ABSOLUTE DOMAIN LAW

Before any code is written, every engineer reads this once and recites it back.

**DOMAIN WALLS ARE ABSOLUTE.** No domain reads another domain's raw data under any circumstance. The Digital Twin reads summaries only, never raw records. Project Management reads nothing from any personal domain, ever. The History Graph is write-only from domains and read-only by the user. Mental health data has a separate encryption layer that cannot be broken even if the primary session key is compromised.

The only approved data flows are:

- Finance sends financial milestone events to History Graph. Finance sends a computed summary to Digital Twin.
- Health sends health event markers to History Graph. Health sends a status-only summary to Digital Twin. Mental health within Health has its own sub-encryption and never sends raw data anywhere.
- Projects send professional completion events to History Graph. Projects send task summary to Digital Twin. Projects receive team member names from Social Graph only, nothing else.
- Social Graph sends relationship event markers to History Graph. Social Graph sends contact summary to Digital Twin. Social Graph sends team member names to Projects.
- History Graph sends major life event markers to Digital Twin. History Graph never sends clinical detail, financial amounts, or relationship specifics.

Any code that violates these flows raises a `CrossDomainViolation` exception. There are no exceptions to this rule. There are no emergency bypasses. There is no admin override.

---

### PART 2 — SYSTEM ARCHITECTURE OVERVIEW

The system runs across seven planes.

**PLANE 1 is the Edge.** A Rust gateway built with Axum handles every incoming request. It does JWT decoding, rate limiting per tenant, complexity classification, and cache checking. Target latency is under 30 milliseconds at P95. Nothing expensive happens here.

**PLANE 2 is Control.** The Python execution orchestrator decides which lane a request goes to. The Auto Mode Engine escalates only when necessary. The Cost Router enforces budget. The Prompt Hub resolves layered prompt templates. Target is under 50 milliseconds combined.

**PLANE 3 is Context.** The Context Selector retrieves relevant memories, knowledge graph nodes, and session state in parallel. The Budget Manager enforces a hard limit of 4000 tokens. The Compactor compresses when over budget. The Decryption Boundary is the only place in the system where encrypted user data becomes plaintext. Target is under 200 milliseconds.

**PLANE 4 is Intelligence.** The Deliberation Engine runs Chain of Thought, ReAct loops, Tree of Thoughts, and Graph of Thoughts depending on complexity. The Council Engine runs multi-model debates for critical decisions. The Reflexion Engine runs asynchronously after task completion to write verified lessons to memory.

**PLANE 5 is Crew.** Domain crews of five agents handle complex multi-step tasks. Map plans the task. Scout gathers information. Run executes tools. Gate validates output. Sync orchestrates the loop and enforces budget. Target is under 5 seconds at P95 for complexity 4 and 5 tasks.

**PLANE 6 is Knowledge.** The Memory Service operates across four tiers: Redis for warm recent context, PostgreSQL for persistent episodic memory, Qdrant for semantic vector search, and Neo4j for structured knowledge relationships. The Knowledge Graph stores claims, sources, entities, and metrics with contradiction detection.

**PLANE 7 is Infrastructure.** The Model Pool manages multiple AI providers with quota-aware failover. The Encryption Service handles end-to-end encryption. The Reliability Layer provides circuit breakers, retry policies, and fallback chains. The Observability Stack tracks every metric, trace, and log.

---

### PART 3 — DIGITAL TWIN

The Digital Twin is a live computed model of you. It is not a database. It does not store raw records. It stores computed state derived from summaries of all your domains. It answers the question: if BIS had to describe you in five seconds to a new agent, what would it say?

The Twin holds your identity constants that never change after setup: preferred name, timezone, primary language, communication style, decision style.

The Twin holds your life context that updates when significant events occur: career phase ranging from student through early career to mid career to senior to transition to retired, family status ranging from single through partnered to parenting to caring for parent, health status as a single word excellent or good or managing or recovery or chronic, financial phase as building or stable or growing or drawdown or recovery, current stress level, and the most recent major life event with its date.

The Twin holds your weighted priorities that update weekly. Each priority has a domain, a human readable description, a weight from zero to one summing to one across all priorities, and a source indicating whether it was explicitly set by you, inferred from your behavior, or suggested by the system.

The Twin holds attention flags that update daily. These are things needing your attention right now. Each flag has a domain, a severity level of info or warning or urgent or critical, a human readable message with no raw data exposed, an action hint, and an expiry time.

The Twin holds your behavioral profile that updates slowly. This captures your peak productivity hours, preferred response length, risk tolerance, planning horizon, feedback preference, and the topics you most frequently ask about.

The Twin holds a summary of your active goals across all domains, with progress percentages and deadlines but no raw financial amounts or clinical data.

The Twin never writes back to any domain. It is a read-only mirror. Agents read from it to personalize their behavior. Nothing writes to it except the async Twin Updater job that runs after domain events.

The Twin Updater is never in the request path. It runs after events like a budget period ending, a health checkup completing, a project finishing, or a relationship silence being detected. It calls each domain's summary interface, never the raw data interface, and computes a new twin version. The last ten versions are kept for diffing.

Every agent receives a TwinContext object injected into its briefcase. This is a lightweight read: preferred name, communication style, decision style, current life phase, top three priorities, active attention flags, and behavioral hints. Never the full twin, never raw domain data.

---

### PART 4 — PERSONAL FINANCE DOMAIN

The Finance Domain owns every financial record of your life from your first bank account to your final estate.

What it covers: all bank accounts checking savings credit investment loan and mortgage, all income streams salary freelance passive rental, all expenses with automatic categorization and subcategory, budgets by category and period with rollover support, financial goals emergency fund vacation house down payment retirement debt payoff custom, investment portfolio across stocks bonds ETFs and crypto, debt management with payoff plans and interest tracking, net worth calculation at every point in time with historical trend, tax-related categorization, subscription tracking showing every recurring charge, bill management with due dates.

What it deliberately does not cover: health-related spending is tracked as an expense category but never analyzed as health data. Professional income is tracked but career trajectory lives in History Graph. Family member finances live in their own twin and require explicit consent to view jointly.

The core data structures are:

**Account** holds institution name, account type, user-assigned nickname, currency, current balance encrypted at rest, credit limit if applicable, interest rate, whether it is the primary account, when it was linked, and when it was last synced.

**Transaction** holds the account, amount where negative means expense and positive means income, raw bank description encrypted, a BIS-cleaned merchant name, automatic category and subcategory, merchant name and location, date, whether it is recurring with a link to the recurring item, user tags and notes, and whether it is excluded from analysis.

Transaction categories span: salary, freelance income, investment income, rental income, other income on the income side, then rent and mortgage, utilities, home maintenance for housing, then groceries, dining, transport, health expenses, clothing for daily living, then savings transfers, investments, debt payments for financial movements, then entertainment, travel, subscriptions, education for lifestyle.

**Budget** holds a category, period monthly or weekly or annual, the budget limit, whether unused budget rolls over, the current amount spent as a computed field, the remaining amount as a computed field, an alert threshold defaulting to 80 percent, and the period start and end dates.

**Financial Goal** holds title, goal type, target amount, current amount, monthly contribution, target date, the linked account that holds this money, priority rank, and computed fields for progress percentage, estimated months remaining, and whether it is on track.

**Net Worth Snapshot** is computed daily and never modified after creation. It holds total assets, total liabilities, net worth, and a breakdown by asset and liability type. This creates a permanent historical record of your financial trajectory.

The finance intelligence agents are:

**FinanceScout** pulls transactions from connected accounts through open banking APIs, runs ML classification for categories accepting user corrections as training signal, detects recurring patterns, and flags anomalies like unusual merchants or unusual amounts.

**FinancePlanner** runs budget versus actual analysis, calculates goal progress, forecasts cash flow for the next 30, 90, and 180 days, models debt payoff scenarios, and runs what-if analysis such as what happens to my goals if I cut dining spending by 30 percent.

**FinanceAlert** sends low balance warnings, budget overrun alerts at the configured threshold, bill due reminders 3 days and 1 day in advance, unusual transaction flags for review, goal milestone celebrations, and periodic subscription audits showing the full list of active recurring charges.

The only events Finance sends to History Graph are: goal achieved, debt paid off, major purchase like a house or car, significant income change, user-tagged financial crisis event, and net worth milestones at 10K 100K 500K 1M and so on. No transaction amounts, no balance details, only event type plus a category like milestone and the date.

Finance across your whole life means: your first salary, your first investment, your debt accumulation and payoff journey, your home purchase, your children's education fund, your retirement savings progress, and eventually your drawdown phase. All of it tracked, analyzed, and advised on by agents that know your full financial history.

---

### PART 5 — HEALTH BANK

The Health Bank is the most private domain in the system. Every piece of data is Tier A encrypted meaning end-to-end with a key that never leaves your device. Mental health data within Health Bank has an additional sub-encryption layer derived from your master key plus a mental health salt. Even if your primary session key is compromised, your mental health records remain protected.

Health data is never used to train any model. Health data is never shared with any other domain except the two approved bridges: event markers to History Graph with no clinical detail, and a single status word to Digital Twin.

What Health Bank covers: medical conditions with ICD codes and status, all medications current and historical with dosage and refill tracking, all appointments upcoming and historical with pre and post notes, all lab results blood work imaging and other diagnostics, vital signs blood pressure heart rate weight temperature blood glucose and more as time series data, mental health including mood tracking therapy notes assessments and journals, fitness including daily activity sleep nutrition and hydration, genetic information and family health history, insurance coverage claims and deductibles, a daily symptoms log, allergies and contraindications, and vaccination records.

What Health Bank deliberately does not cover: health-related financial transactions live in Finance. Health impact on work performance goes to History Graph only through event markers. Mental health impact on relationships goes to History Graph only.

The core data structures are:

**Medical Condition** holds the condition name, ICD-10 code where known, status as active resolved managed or monitoring, diagnosis date, resolution date, diagnosing provider, encrypted notes, linked medications, and linked documents.

**Medication** holds name, generic name, dosage, route of administration oral topical injection inhaled, frequency, prescribing provider, what condition it was prescribed for, start date, end date, whether it is active, refill date, refills remaining, user-reported side effects, and encrypted instructions.

**Health Appointment** holds provider name and type, specialty, appointment type as checkup followup procedure therapy or emergency, scheduled time, location, whether it is telehealth, status as upcoming completed missed or cancelled, encrypted pre-appointment notes for what to discuss, encrypted post-appointment notes for what was discussed, and any documents generated like referrals or summaries.

**Vital Sign Entry** is a time series record. Each entry holds measurement time, source as manual device or provider, device identifier if applicable, and all the possible vital measurements: systolic and diastolic blood pressure, heart rate, weight in kilograms, height in centimeters, BMI computed from weight and height, temperature in celsius, blood oxygen percentage, blood glucose, and HbA1c. Only the measurements actually taken are recorded.

**Mental Health Entry** is the most sensitive record in the entire system. It requires the additional mental health sub-key to decrypt. It holds the entry type as mood log therapy note formal assessment journal or crisis flag. Mood logs capture mood score energy level anxiety level and sleep quality each on a 1 to 10 scale. Therapy entries capture therapist name session number and therapy type CBT DBT Psychodynamic EMDR. Assessment entries capture the assessment type PHQ-9 or GAD-7 or others, the score, and the clinical interpretation. All free text content is encrypted with the mental health sub-key. A crisis flag immediately generates an urgent attention flag in the Digital Twin and triggers resource display. Mental health entries are never in AI context unless you explicitly invoke mental health reflection mode.

**Fitness Entry** is a daily log. It holds date, source as manual or Apple Health or Garmin or Fitbit or Google Fit, step count, active minutes, individual workout records, sleep start and end time, total sleep hours, sleep quality, deep sleep hours, REM sleep hours, calories consumed, macronutrients protein carbs fat, water intake, and body composition from smart scale if available.

The health intelligence agents are:

**HealthScout** pulls from connected health devices and apps, runs OCR on uploaded lab reports and medical documents to extract structured data, monitors medication refill deadlines and generates reminders, and flags gaps in vitals logging.

**HealthAnalyst** runs trend analysis such as blood pressure trending upward over three months, detects correlations such as poor sleep preceding low mood preceding poor diet the next day, tracks medication adherence, interprets lab results with appropriate not-medical-advice disclaimers, and tracks progress toward fitness goals.

**HealthCoordinator** manages appointment scheduling reminders, tracks whether referred specialist appointments were actually booked, tracks insurance claim status, sends prescription refill reminders two weeks and three days in advance, and generates pre-appointment preparation summaries of what to discuss and what documents to bring.

**MentalHealthGuardian** is a completely separate agent with no access to any other domain. It analyzes mood trends over time, detects potential crisis indicators from sudden score drops or specific language patterns, detects therapy session gaps, maintains a consistently gentle non-clinical tone, links to appropriate resources when needed, and never shares any mental health data with any other system component.

Health across your whole life means: your birth records and childhood vaccinations, your first diagnoses, your medication history across decades, your fitness evolution, your mental health journey including therapy and growth, your chronic condition management, your aging and the health events that shape it, and eventually your end-of-life care documentation. All of it private, all of it yours.

---

### PART 6 — PROJECT MANAGEMENT DOMAIN

Project Management has zero connection to personal domains. This is an architectural constraint, not a configuration setting. Project agents receive no TwinContext, no HealthContext, no FinanceContext. They can reference Social Graph for team member names and contacts only. They can write professional events to History Graph only.

The reason is simple: work data and personal data should never mix. Your health status should not leak into your project context. Your financial situation should not influence how your project agent advises you. Team members referenced in a project get no access to your personal life domains whatsoever.

What Project Management covers: all projects personal work side-projects learning and open-source, all tasks with full structure including subtasks dependencies and checklists, milestones with completion tracking, decision records capturing context rationale and eventual outcome, meeting and idea notes, team member references with roles only, time tracking estimated versus actual, velocity tracking, deadline risk analysis, and project briefings for daily standups weekly reviews and pre-meeting context.

The core data structures are:

**Project** holds title, description, status as planning active on-hold completed archived or cancelled, priority as critical high medium or low, project type as personal work side-project learning or open-source, timeline with start date and target date, team members list with roles only, tags, parent project for sub-projects, linked related projects, and computed metrics for task count completion count overdue count and completion percentage.

**Task** holds title, description, status as todo in-progress blocked in-review done or cancelled, priority, assignment to a Social Graph person by name only with no personal data, creator, timeline with due date estimated hours and actual hours, parent task for subtasks, subtask list, task dependencies, tags, checklist items, attachments, and blocker information if blocked.

**Milestone** holds title, description, due date, completion status, completion timestamp, and the list of linked tasks.

**Project Decision** is a critical record. It captures context meaning what situation prompted this decision, the decision itself, alternatives that were considered, the rationale, who made it, when it was made, and later what the outcome was. This creates a permanent institutional memory for every significant decision in your professional life.

**Project Note** captures meeting notes, ideas, research findings, blocker descriptions, and feedback with links to the relevant project and optionally the relevant task.

**Team Member** is a lightweight reference: an optional link to a Social Graph person, a display name for this project, their role such as designer or dev lead or client, whether they are external, and a contact hint like email them rather than the actual email address.

The project intelligence agents are:

**ProjectPlanner** decomposes project goals into complete task trees, estimates timelines based on task complexity and your historical velocity, identifies dependencies that might create bottlenecks, suggests milestones, and proactively identifies structural gaps such as a project missing a testing phase or a launch plan.

**ProjectMonitor** tracks task completion rates against plan, identifies tasks that have been blocked for too long, detects deadline risk by counting tasks due in the next period versus tasks completed per day at current velocity, and tracks velocity trends over the project's life.

**ProjectBriefing** generates your daily standup summary of what is due today and what is blocked, your weekly review of what was accomplished and what slipped, pre-meeting context when you have a call with someone about a project with full status, risk alerts when a project milestone is at risk, and post-project retrospectives capturing what worked and what did not.

Projects across your whole life means: your school assignments, your university research projects, your first work projects, your side businesses, your open source contributions, your creative projects, your lifelong learning projects for every new skill or field, your entrepreneurial ventures, and your personal projects from home renovation to writing a book. All tracked, all connected to your professional history, none leaking into your personal health or financial records.

---

### PART 7 — STUDY AND LEARNING AS PROJECTS

Study and learning are a category of project in the Project domain. They get their own project type of learning and their own specialized agent behaviors.

A learning project has all the structure of a regular project plus a curriculum structure where the milestones are learning modules or chapters, the tasks are study sessions and exercises and assessments, and the decision records capture conceptual breakthroughs and things that clicked versus things that needed revisiting.

The ProjectPlanner in learning mode decomposes a learning goal into a curriculum, estimates time based on the complexity of the subject and your historical learning velocity, identifies prerequisite dependencies between topics, and creates spaced repetition reminders as tasks.

For research projects the same structure applies with additional task types for literature review, hypothesis formation, experiment design, data collection, analysis, and write-up. Decision records become research decisions capturing why a methodology was chosen and what the outcome was.

For coding projects tasks map to features and bug fixes and refactors, milestones map to releases, and the codebase itself links as an attachment to the project. The ProjectBriefing in coding mode generates commit-level context summaries before work sessions.

All intellectual work from learning a new programming language to researching a medical condition to building a product to writing a thesis runs through this domain. The History Graph captures the professional milestones: course completed, skill acquired, project shipped, degree earned, research published.

---

### PART 8 — SOCIAL GRAPH DOMAIN

The Social Graph is not a contact list. It is a relationship model that understands who people are to you, your history with them, what you know about them, how different groups in your life relate to each other, and who should be considered when making a given decision.

What it covers: every person in your life with their relationship type to you, your relationship history with each person, what you remember about them including preferences birthdays and important dates, group memberships and group dynamics, interaction logging with sentiment, silence detection when you have not contacted someone you care about, and upcoming important date tracking across your entire network.

The consent model is critical. Everything in the Social Graph is your memory of other people, not their data. You remember John's birthday because you noted it, not because John entered it into your system. This means the data belongs to you, is stored in your twin, is never shared with the person it concerns without explicit consent, and is never used to construct a profile of that person for any external purpose.

Relationship types span: self, partner, child, parent, sibling, grandparent, grandchild, extended family on the family side, then close friend, friend, acquaintance on the friendship side, then colleague, manager, direct report, mentor, mentee, client, vendor on the professional side, then doctor, therapist, and caregiver for care relationships.

Privacy tiers determine what the system can surface in different contexts: intimate tier for partner and children allows high data sharing in relevant contexts, close tier for close friends and parents allows moderate sharing, social tier for friends and colleagues allows limited sharing, professional tier for work contacts shows work data only, minimal tier for acquaintances shows name and context only.

**Person** record holds full name, preferred name, nickname, pronouns, relationship type, relationship group such as immediate family or work team or college friends, closeness level from 1 to 5, privacy tier, encrypted contact information phone email address and social handles, known information about them including birthday birthplace occupation interests and preferences, important dates with their types, how you met them, an encrypted shared history summary you wrote, last interaction date and your target interaction frequency, and the computed upcoming important dates within 30 days.

**Relationship** record captures how two people in your graph relate to each other, not just how they relate to you. This allows the system to understand that two colleagues are also married to each other, or that two friends who used to be close had a falling out. You note this context, and the system uses it to give better advice when those people are relevant to a decision.

**Group** record captures labeled collections of people: your immediate family, your college friend group, your work team, your community group. Each group has its own shared context description capturing what this group is about.

**Interaction Log** captures significant interactions, not every message. A dinner with a close friend is worth logging. An email thread about scheduling is not. Each log entry captures the interaction type, date, duration, location, an encrypted summary of what was discussed, your sentiment tag of good neutral or difficult, and whether there is a follow-up needed.

The social intelligence agents are:

**RelationshipScout** monitors upcoming important dates for your entire network with appropriate lead time so you have time to prepare, detects silences when you have not contacted someone you care about beyond your target frequency, tracks relationship health signals, and surfaces relevant connection context when you are visiting a city where contacts live.

**GroupCoordinator** handles family gathering planning context by pulling together what you know about the group, generates gift suggestions based on known preferences and upcoming dates, maintains awareness of group dynamics including noted conflicts or tensions, and retrieves shared history when you need context before a significant interaction.

**RelationshipMemory** retrieves what you know about a specific person on demand: the last conversation topic, things they mentioned that were significant, follow-ups you owe them, and a summary of your relationship history across years.

Social Graph across your whole life means: the people who are present from your birth your family, the friendships you form in childhood and school, your professional network as it builds across your career, your romantic relationships, your children if you have them, their networks as they grow, the mentors who shaped you, the colleagues who became friends, and the people you lose to death or distance but whose memory matters to your history. All of it tracked, all of it yours, none of it shared without your consent.

---

### PART 9 — HISTORY GRAPH DOMAIN

The History Graph is the long-term memory of your entire life. It is a personal temporal knowledge graph, a timeline of every significant event in your life, connections between events across domains, and your memories about the people close to you. No other component has a view this complete. Each domain only sees its own records. Only the History Graph and therefore only you see the full picture of your life.

It answers questions like: when did I first deal with this health condition, what was happening in my career when that personal crisis occurred, what do I remember about my father's illness, how has my mental health evolved over the past decade, what were the turning points that led me to my current career, what was I learning when I met my partner.

The most critical design decision is memory attribution. Every memory node has a subject. The subject is either yourself or another person identified by their Social Graph ID. This distinction is permanent and non-negotiable. Memories about others are stored in your History Graph because it is your memory, tagged with the other person's identifier, accessible to you when thinking about that person, never shared with that person without explicit consent, and never used to build a profile of that person.

**Memory Node** holds: when the event occurred and when it was recorded, an optional period label you assign like college years or Barcelona chapter or Dad's illness, the subject attribution as self or person with relationship context, the domain as health mental-health professional financial relationships education personal-growth family travel creative loss-and-grief achievement or general, an event type within the domain, a short human-readable title, the full encrypted memory content, a confidence score from 0 to 1 for how sure you are it is accurate, the source as self-reported or auto-generated from a domain event or reconstructed or AI-assisted, links to related memories, links to people mentioned, causal links to memories that caused this one and memories this one led to, searchable tags, location, privacy level as private personal close-only or family, a sealed flag meaning this memory is never surfaced in AI context under any circumstances, sentiment as positive negative neutral or complex, and an emotional weight from 0 trivial to 1 life-defining.

**Life Chapters** are named periods in your life. They can be auto-detected from memory density and major event clusters or manually defined by you. A chapter has a title, start and end dates, a description, the dominant memory domains of that period, and an overall sentiment. Examples are college years, first job in London, Dad's illness, the startup years, the recovery period, new parenthood.

**Memory Chains** are the most powerful feature. They explicitly link sequences of memories across domains, showing how one life event caused another. The example in the architecture document shows how a parent's cancer diagnosis led to a remote work arrangement which coincided with anxiety and sleep problems which led to starting therapy which ran through the parent's death which eventually led back to office work and then a promotion. This chain is invisible to any single domain. Finance only sees its piece. Health only sees its piece. Only the History Graph shows the full chain. Only you can see how your life actually connected.

Memory Chains have a title, an ordered list of memory nodes, the relationship type between each consecutive pair as caused or led-to or concurrent, and the time span from first to last event with an open end if ongoing.

The events each domain sends to History Graph are:

From Finance: goal achieved, debt paid off, major purchase, income change, financial crisis user-tagged, net worth milestone. No transaction amounts, no balance figures.

From Health: major diagnosis, surgery or procedure, condition resolved, significant medication started, significant fitness milestone like first marathon or weight goal reached, mental health milestone like starting therapy or a recovery milestone. No clinical detail, no scores, no lab values, no medication names.

From Projects: project completed, major milestone reached, project failed or cancelled with user notes, skill demonstrated where you tag what you learned, notable collaboration where you tag the team experience. No task details, no team member personal information.

From Social: relationship formed, significant relationship change, loss through death or distance, reconnection after long absence, relationship health milestone. No interaction details, no personal information about the other person.

The History Graph intelligence agents are:

**HistoryScout** builds timeline views on request filtered by subject, domain, date range, or life chapter. It detects potential memory chains by finding memories close in time across different domains and suggests linking them. It never forces connections, only suggests them for your confirmation.

**HistoryAnalyst** runs pattern recognition across years answering questions like what your best professional periods had in common, what life events preceded major career changes, how your relationship with a person evolved over a decade, or what the emotional arc of a particular chapter looks like. It generates grief support timelines showing all your memories about someone who passed. It connects mental health patterns to life context with appropriate privacy protections.

**Memory Attribution Enforcer** is not an agent but a system rule. Every memory query must specify whether it is self context or other person context. Memories with the sealed flag are never included in AI context under any circumstances. Mental health memories require explicit user invocation through a reflection mode. Memories about others require the relationship context to be specified.

History Graph across your whole life means: birth records entered by your parents or reconstructed later, childhood memories that shape you, educational milestones, the relationships that defined each chapter, the health events that changed your trajectory, the professional decisions that built your career, the losses that left marks, the achievements that defined you, and eventually the final chapter where your records become part of what you leave behind. From birth to death, all of it connected, all of it attributed, all of it private to you.

---

### PART 10 — THE CROSS-DOMAIN BRIDGE

Every data flow between domains passes through a single CrossDomainBridge class. All other cross-domain access raises CrossDomainViolation. This is enforced architecturally, not by convention.

The approved bridges are:

- Finance to Digital Twin: finance summary only, containing computed status like financial phase and top goals with progress percentages, no amounts, no account details.
- Health to Digital Twin: health status only, a single computed string like managing or good, no conditions, no medications, no lab values.
- Projects to Digital Twin: project summary only, containing count of active projects and overdue tasks, no project names unless user has set them as public in their twin, no team member information.
- Social to Digital Twin: social summary only, containing count of relationships and upcoming important dates within 30 days, no names, no contact details.
- Finance to History Graph: financial events only, the approved event types with date and category but no amounts.
- Health to History Graph: health events only, the approved event types with date and sentiment but no clinical details.
- Projects to History Graph: professional events only, the approved event types with date and user-set tags but no task details.
- Social to History Graph: relationship events only, the approved event types with date but no personal information about the other person.
- History Graph to Digital Twin: major life events only, the most recent major event type and date to populate the life context current life major event field.
- Social to Projects: team member names and contact hints only, to allow project assignment without leaking personal data about team members.

The CrossDomainBridge implementation validates both the source-target pair and the data type against a whitelist. If either does not match an approved entry, it raises CrossDomainViolation with full details of the attempted violation. This exception is logged as a critical security event.

---

### PART 11 — ENCRYPTION ARCHITECTURE

All user data is end-to-end encrypted. This means encrypted on your device, transmitted encrypted, stored encrypted on the server, and decrypted only for the duration of a single LLM execution window.

The encryption tiers are:

**Tier A** is end-to-end encrypted with your session key. All Health data, all Finance amounts and account details, all Social contact information and relationship notes, all History Graph memory content. The server never sees plaintext Tier A data except in the controlled decryption window during execution.

**Tier B** is server-encrypted. System-derived data like knowledge graph nodes, aggregated embeddings, and tool metadata. The server can decrypt this for operations because it is not your private personal data.

**Tier C** is plaintext. Operational data like execution metadata, routing decisions, cost metrics, and system telemetry. Nothing sensitive is ever in Tier C.

Mental health data is Tier A with an additional sub-key. The sub-key is derived from your User Master Key combined with a mental health salt. Breaking your primary session key does not decrypt mental health records.

The key model uses a User Master Key generated on your device and never transmitted to any server. A Session Key is generated per session, encrypted with your UMK, and sent to the server. The server stores encrypted session key and encrypted data but never your UMK and therefore cannot independently decrypt your data.

The decryption boundary is a single class called ContextDecryptionBoundary. Only this class calls the EncryptionService decrypt method. Decrypted data is used in the execution window and then wiped using ctypes memory zeroing, not Python's garbage collector which does not guarantee immediate memory reclamation.

Rules that are never violated: decrypted data is never persisted, never logged, never cached, never reused across tenants. Logs always show encrypted payload length indicators, never content. Each tenant's keys are completely separate.

---

### PART 12 — AI AGENTS ACROSS YOUR LIFE

The agents that serve you across all domains understand your Digital Twin context and therefore understand who you are right now: your life phase, your priorities, your behavioral preferences, and what needs your attention. They do not need to be told your context repeatedly. They know it.

For financial questions they know your financial phase, your top financial priorities, your risk tolerance from your behavioral profile, and any active budget alerts. They give advice calibrated to where you actually are, not a generic person.

For health questions they know your health status summary from the Digital Twin but nothing clinical. If you ask about a health topic, HealthAnalyst is invoked with your actual health records under the appropriate encryption and privacy protections.

For project questions they know how many active projects you have and whether you have overdue tasks. They do not know your health or finances. ProjectPlanner works in a clean professional context.

For relationship questions RelationshipMemory pulls what you know about the relevant person from your Social Graph and surfaces it in a natural way: last time you spoke you were discussing their job change, they mentioned their mother was ill, you noted you owe them a follow-up.

For life questions the History Graph agents can surface patterns across your entire history: the periods when you were most productive and what conditions created them, how your health has evolved alongside your career, what your relationship history with a specific person looks like across years.

For learning questions the Project domain handles curriculum building, spaced repetition scheduling, and progress tracking. The HistoryAnalyst can surface how your previous learning experiences went and what approaches worked for you based on your pattern history.

For coding questions the Project domain manages the technical work. The Knowledge Graph stores technical claims and solutions. The Deliberation Engine handles complex technical reasoning with ReAct loops for multi-step problems and the Council Engine for critical architectural decisions.

For brainstorming and ideation the Deliberation Engine's Tree of Thoughts mode generates multiple parallel reasoning branches, explores them, and synthesizes the best ideas. The Knowledge Graph provides structured context from everything the system knows about the relevant domain.

For mental health support the MentalHealthGuardian agent monitors your mood trends, detects concerning patterns, maintains appropriate tone, and connects you to resources. It is completely isolated from your professional and financial life. It does not give clinical advice but it remembers your history, notices patterns, and is always there.

---

### PART 13 — LIFE COVERAGE FROM 0 TO 100 PERCENT

The system is designed to grow with you across every stage of life.

In early childhood your parents or guardians set up your Health Bank with birth records, vaccination history, and pediatric records. Your History Graph begins. Your Social Graph contains your family.

In school years your Project domain fills with learning projects. Your History Graph captures educational milestones. Your Social Graph grows with friendships and teachers. Your Health Bank tracks your health history. Your Finance domain might start with pocket money tracking or a first savings goal.

In university your Project domain handles research, coursework, and social activities. Your Finance domain tracks student loans, part-time income, and budgeting on limited income. Your Social Graph captures the friendships and mentors of this formative period. Your History Graph captures the milestones and the chapters.

In early career your Finance domain tracks salary, builds emergency fund, starts investment. Your Project domain manages professional work, learning new skills, side projects. Your Social Graph captures colleagues and professional network. Your Health Bank tracks the baseline health that will matter for the rest of your life. Your History Graph records the professional milestones and early relationship history.

In mid career your Finance domain manages growing complexity: investments, property, insurance, family financial planning. Your Project domain handles complex professional work, team management, strategic decisions recorded as Project Decisions. Your Social Graph maintains your network of hundreds of meaningful relationships with reminders to stay connected. Your Health Bank tracks the conditions that begin to emerge. Your History Graph shows the arc of your professional and personal growth across a decade.

In family years your Social Graph expands to include your partner, children, and their evolving networks. Your Finance domain handles family budgeting, children's education funds, joint financial planning. Your Health Bank tracks your family members' health insofar as they share it with you. Your History Graph captures the family milestones.

In senior career your Finance domain manages peak earning, retirement planning, estate considerations. Your Project domain handles mentoring, strategic leadership, and knowledge transfer. Your History Graph provides rich context for every major professional decision drawing on decades of pattern history.

In transition and retirement your Finance domain shifts to drawdown planning and estate management. Your Health Bank becomes more active tracking more complex health management. Your History Graph becomes a living memoir. Your Social Graph helps maintain the relationships that matter most as professional networks naturally thin.

In later life your Health Bank manages complex multi-condition health with medication interactions, appointment coordination, and insurance navigation. Your History Graph becomes the record of a life well-documented. Your Social Graph helps maintain connection to the people who matter. Your Finance domain manages drawdown and eventual estate records.

The History Graph ultimately becomes your legacy data: the record of who you were, what you valued, what you built, who you loved, and what happened to you. Accessible to people you designate when you choose to share it.

---

### PART 14 — STORAGE ARCHITECTURE

Finance domain uses PostgreSQL for accounts, transactions, budgets, goals, and net worth snapshots. Redis caches current balances and budget usage with a one-hour TTL. TimescaleDB handles transaction time series and net worth history for efficient time range queries. All financial amounts are Tier A encrypted. Metadata is Tier B.

Health domain uses PostgreSQL for conditions, medications, and appointments all encrypted. TimescaleDB handles vital signs, mood scores, and fitness entries as time series. An S3-compatible object store with encryption handles medical documents and lab PDFs. Redis caches upcoming appointments and medication reminders. All health data is Tier A. Mental health data has the additional sub-key layer.

Project domain uses PostgreSQL for projects, tasks, milestones, decisions, and notes. Redis caches active project status with a five-minute TTL. Encryption is Tier B since project data is not personal health or finance data, though still private.

Social Graph domain uses Neo4j for person nodes, relationship edges, and group memberships to enable efficient graph traversal for queries like who do I know in this city or how are these two people connected. PostgreSQL handles interaction logs and important dates. Redis caches upcoming important dates. Contact details are Tier A. Relationship metadata is Tier B.

History Graph domain uses Neo4j for memory nodes, chain relationships, and temporal edges. Qdrant stores memory embeddings for semantic search enabling queries like find memories about times I felt lost or memories about my relationship with my father. PostgreSQL handles memory metadata and audit trail. All memory content is Tier A. Mental health memories have the additional sub-key. Redis caches recent memories with a 15-minute TTL.

---

### PART 15 — BUILD SEQUENCE

**Phase D1** is foundation running alongside core platform build. This establishes domain isolation enforcement with the CrossDomainBridge and comprehensive tests that verify violations are caught. Digital Twin schema and TwinContext builder are created. Stub twin summaries for all domains are created. The twin update job framework is established.

**Phase D2** is Finance domain. Account and Transaction schemas are built. Transaction classification starts rule-based and transitions to ML with user corrections as training signal. Budget management, goal tracking, and net worth calculation are built. Finance to Digital Twin summary interface and Finance to History Graph events are built.

**Phase D3** is Health domain. Core health schemas for conditions medications appointments and vitals are built. Fitness entry ingestion from Apple Health, Garmin, and manual entry is built. Vital trend analysis is built. The mental health sub-domain is built with additional encryption and the separate MentalHealthGuardian agent. Health to Digital Twin status summary and Health to History Graph events are built.

**Phase D4** is Project Management. Project and Task schemas are built. Milestone tracking and decision recording are built. The project briefing agent, velocity tracking, and deadline risk analysis are built. Strict isolation tests verifying no personal domain access are run.

**Phase D5** is Social Graph. Person and Relationship schemas in Neo4j are built. Group management, interaction logging, important date tracking, silence detection, and the consent model implementation are built.

**Phase D6** is History Graph. Memory node schema and Neo4j storage are built. The attribution system distinguishing self from other is built. Cross-domain event ingestion from all four domains is built. Timeline builder, chain detection with user confirmation flow, semantic search over memories using Qdrant, and privacy controls including the sealed memory gate and mental health gate are built.

**Phase D7** is Digital Twin completion. All domain summaries are connected to the twin updater. Behavioral profile learning from interaction patterns is built. Attention flag generation across all domains is built. TwinContext injection into all agents is verified. Twin version history is completed.

---

### PART 16 — PRIVACY PRINCIPLES THAT ARE NEVER NEGOTIATED

Domain data never crosses walls raw. Only summaries and events pass through the CrossDomainBridge.

Mental health is double-encrypted. Not accessible even if the primary session key is compromised. Not accessible to any agent without explicit user invocation. Not sent to any other domain in any form.

Memories about others belong to the person who remembers them. They are stored in your History Graph. They are never shared with the subject without explicit consent. They are never used to build a profile of the subject for any external purpose.

Sealed memories are never in AI context. Not even the most privileged agents can see them. The user sets them as sealed and they remain sealed.

History Graph is write-mostly. Domain events write to it. Only HistoryScout and HistoryAnalyst read from it, and only when explicitly invoked by the user. It is never part of default agent context.

Project data never touches personal data. The isolation is architectural. If you ask how your health is affecting your work, the History Graph answers it by showing patterns across both domains from a life perspective, not by creating a direct bridge between Health and Projects.

The Digital Twin is a mirror not a master. It reflects domain data. It does not control domains. Agents read TwinContext to personalize their responses. They do not modify the twin directly. The twin is always a computed view, never a source of truth.

The user is always the final authority. The system advises, reminds, analyzes, and plans. It does not act on your life without your confirmation except for reminders and alerts which are notifications not actions.

---

This is the complete architecture. Every dimension of human life from birth to death, from first rupee to final estate, from first vaccination to last prescription, from first friendship to final relationships, from first school project to career legacy, from earliest memory to life memoir. All of it managed, all of it private, all of it yours.

---

# BIS v2 Production Technical Architecture

**Document Type:** Technical Architecture / Implementation Specification
**System:** Butler Intelligence System v2
**Short Name:** BIS v2
**Status:** Draft for implementation review
**Audience:** Engineering, Architecture, Security, Data/AI, SRE, Product
**Owner:** Platform Architecture
**Last Updated:** 2026-04-27

---

## 1. Executive Summary

BIS v2 is a privacy-preserving personal intelligence operating system. It coordinates user context, memory, tools, domain agents, and long-running workflows across finance, health, projects, social relationships, personal history, and learning.

The system is not a chatbot wrapper. It is a governed AI runtime with strict execution lanes, isolated domain ownership, encrypted memory, explicit cross-domain bridges, bounded reasoning, tool policy enforcement, and auditability.

The core architectural objective is simple:

> Route every request through the cheapest safe execution path while preventing raw domain data from crossing security boundaries.

BIS v2 is built around five mandatory constraints:

1. **Domain isolation:** Each domain owns its own raw data and exposes only approved summary/event interfaces.
2. **Computational gravity:** Requests escalate only when complexity, risk, or tool dependency requires it.
3. **Policy-gated action:** Agents cannot execute tools directly. Every action passes through policy, routing, quota, sandbox, and audit layers.
4. **Encrypted personal memory:** Sensitive user data is encrypted by tier and decrypted only inside controlled execution windows.
5. **Human authority:** The system may recommend, remind, summarize, and prepare actions, but high-impact actions require explicit user approval.

---

## 2. System Goals

### 2.1 Primary Goals

- Provide a unified personal intelligence runtime across life domains.
- Maintain strict separation between raw finance, health, project, social, and history data.
- Support low-latency answers for simple requests and durable multi-agent execution for complex workflows.
- Support multi-tenant deployment with tenant-specific policies, budgets, keys, tools, and model routing.
- Preserve privacy through end-to-end encryption, tiered data classification, and explicit decryption boundaries.
- Provide observable, testable, production-grade runtime behavior.

### 2.2 Non-Goals

BIS v2 does **not** aim to:

- Replace doctors, therapists, financial advisors, lawyers, or emergency services.
- Share one user's personal graph with another user without explicit consent.
- Train foundation models on raw private user data.
- Allow agents to bypass policy for convenience.
- Treat project/work context as automatically eligible for personal context.
- Store hidden chain-of-thought traces as user-visible truth.

---

## 3. Core Architecture Laws

### 3.1 Domain Wall Law

Raw domain data never crosses domain boundaries.

Domains communicate through approved bridge payloads only. A domain may emit:

- **Summaries** to the Digital Twin.
- **Events** to the History Graph.
- **Explicitly approved references** to another domain when listed in the Cross-Domain Bridge Registry.

Any unapproved source-target pair raises `CrossDomainViolation` and is logged as a critical security event.

### 3.2 Computational Gravity Law

Every request starts in the cheapest safe lane and escalates only when necessary.

Escalation is based on:

- Intent complexity.
- Tool dependency.
- Safety risk.
- Data sensitivity.
- Required deliberation depth.
- Domain count.
- Tenant budget.
- Historical task behavior.

### 3.3 Frameworks-at-the-Edge Law

Domain logic must not depend on FastAPI, LangChain, database clients, queue clients, cloud SDKs, or model providers.

Allowed dependency direction:

```text
api -> services -> domain
infrastructure -> domain interfaces
workers -> services -> domain
```

Forbidden dependency direction:

```text
domain -> api
domain -> infrastructure
domain -> framework SDK
domain -> model provider SDK
```

### 3.4 Agent Scope Law

Agents are not general-purpose free agents. Every agent has:

- A domain.
- A role.
- Allowed tools.
- Allowed memory scopes.
- Allowed output schemas.
- Risk tier.
- Execution budget.
- Validation policy.

### 3.5 Human Authority Law

The user remains the final authority over high-impact decisions.

The system may autonomously perform low-risk operations such as reminders, summarization, categorization, and read-only retrieval. It must request approval for irreversible, financial, health-sensitive, account-changing, legal, or external-communication actions.

---

## 4. System Context

### 4.1 External Actors

| Actor               | Description                                                | Access Pattern                  |
| ------------------- | ---------------------------------------------------------- | ------------------------------- |
| User                | Primary owner of personal data and task intent             | Client app, web, voice, API     |
| Tenant Admin        | Manages tenant policy, budgets, provider config            | Admin console                   |
| Domain Integrations | Banks, health apps, calendars, email, docs, code hosts     | OAuth/API connectors            |
| Model Providers     | LLM, embedding, reranker, classifier providers             | Provider registry               |
| Tool Providers      | Browser, file, email, calendar, code, search, device tools | Tool registry                   |
| SRE/Security        | Operates infrastructure and monitors incidents             | Observability and audit systems |

### 4.2 Top-Level System Diagram

```text
[Clients]
   |
   v
[Edge Gateway]
   |
   v
[Control Plane: Orchestrator + Routing + Policy]
   |
   +--> [Context Plane: Retrieval + Budget + Decryption Boundary]
   |
   +--> [Intelligence Plane: LLM Runtime + Deliberation + Council]
   |
   +--> [Tool Plane: Tool Registry + Policy + Sandbox]
   |
   +--> [Domain Plane: Finance | Health | Projects | Social | History | Twin]
   |
   v
[Knowledge + Storage + Observability + Audit]
```

---

## 5. Canonical Seven-Plane Architecture

### 5.1 Plane 1: Edge

**Purpose:** Authenticate, normalize, classify, and protect request ingress.

**Primary Components:**

- API Gateway.
- JWT/session decoder.
- Tenant resolver.
- Rate limiter.
- Idempotency guard.
- Request complexity pre-classifier.
- Cache lookup.
- Request envelope builder.

**Responsibilities:**

- Decode identity and tenant context.
- Reject malformed or unauthorized requests early.
- Assign `request_id`, `trace_id`, and `tenant_id`.
- Perform coarse complexity scoring.
- Apply rate limits before expensive work.
- Construct canonical `ButlerEnvelope`.

**Latency Target:** P95 < 30 ms for gateway-only work.

**Must Not:**

- Perform LLM calls.
- Decrypt private user data.
- Execute tools.
- Perform domain business logic.

---

### 5.2 Plane 2: Control

**Purpose:** Decide execution lane, enforce budget, coordinate workflow lifecycle.

**Primary Components:**

- `ExecutionOrchestrator`.
- `IntakeProcessor`.
- `AutoModeEngine`.
- `CostRouter`.
- `PromptHub`.
- `PlanEngine`.
- `RuntimeKernel`.
- `WorkflowRepository`.

**Responsibilities:**

- Validate safety and policy preconditions.
- Redact unsafe or unnecessary input spans.
- Classify user intent.
- Create or resume workflow records.
- Select execution lane.
- Resolve prompt templates from configuration.
- Dispatch execution to deterministic tools, LLM, tool-using agent, domain crew, or async worker.

**Latency Target:** P95 < 50 ms excluding downstream LLM/tool calls.

---

### 5.3 Plane 3: Context

**Purpose:** Retrieve, filter, decrypt, compact, and assemble context safely.

**Primary Components:**

- `ContextSelector`.
- `ContextBudgetManager`.
- `ContextCompactor`.
- `UnifiedRetrieval`.
- `ContextSanitizer`.
- `ContextDecryptionBoundary`.
- `TwinContextBuilder`.

**Responsibilities:**

- Retrieve context in parallel from allowed scopes.
- Enforce context budgets by lane and tenant policy.
- Decrypt only the minimum required encrypted payloads.
- Remove prompt-injection, exfiltration, and tool-hijack payloads from retrieved content.
- Produce a compact `ExecutionContext` for the runtime.

**Latency Target:** P95 < 200 ms for retrieval and context assembly, excluding remote provider latency.

**Security Rule:** Decrypted data must never be logged, persisted, cached, or passed outside the execution window.

---

### 5.4 Plane 4: Intelligence

**Purpose:** Generate answers, reason over context, call tools through controlled interfaces, and validate output.

**Primary Components:**

- `MLRuntimeManager`.
- Provider registry.
- `SmartRouter` / model router.
- `DeliberationEngine`.
- `CouncilEngine`.
- `ReflexionEngine`.
- `OutputValidator`.

**Reasoning Modes:**

| Mode                  | Use Case                                     | Visibility                                |
| --------------------- | -------------------------------------------- | ----------------------------------------- |
| Direct answer         | Simple knowledge/summary tasks               | User-visible final answer only            |
| ReAct-style tool loop | Tool-dependent tasks                         | Tool trace summary, not private reasoning |
| Tree/Graph search     | Complex planning and architecture tasks      | Final synthesized plan only               |
| Council review        | Critical decisions or high-risk architecture | Final consensus and dissent summary       |
| Reflexion             | Post-task learning and memory improvement    | Stored only after validation              |

**Rule:** Private deliberation traces are not treated as user-facing records. Only validated summaries, decisions, and audit metadata may be stored.

---

### 5.5 Plane 5: Crew

**Purpose:** Execute complex multi-step domain workflows using scoped specialist agents.

**Canonical Crew Roles:**

| Role  | Responsibility                                           |
| ----- | -------------------------------------------------------- |
| Map   | Decompose task, produce plan, define acceptance criteria |
| Scout | Retrieve information from approved sources               |
| Run   | Execute approved tools and domain operations             |
| Gate  | Validate correctness, safety, policy compliance          |
| Sync  | Coordinate loop state, budget, retries, final response   |

**Gate Rejection Contract:**

```python
class RejectionDelta(BaseModel):
    rejected_claim: str
    violation_type: Literal["constraint", "quality", "safety", "factual", "schema", "policy"]
    suggested_correction: str | None
    retry_allowed: bool
    retry_budget_remaining: int
```

**Loop Rule:**

A crew may retry only when `retry_allowed = true` and the lane budget permits another iteration. Otherwise, it must return a partial result with failure details.

**Latency Target:** P95 < 5 seconds for bounded complexity 4/5 tasks that do not require external long-running tools.

---

### 5.6 Plane 6: Knowledge

**Purpose:** Store, retrieve, relate, and validate user memory, domain events, and knowledge artifacts.

**Primary Components:**

- Memory Service.
- Knowledge Graph.
- Semantic vector index.
- Episodic memory store.
- Entity and claim store.
- Contradiction detector.
- Source attribution system.

**Storage Tiers:**

| Store        | Role                                                          |
| ------------ | ------------------------------------------------------------- |
| Redis        | Warm short-lived context and session cache                    |
| PostgreSQL   | Durable relational records and audit metadata                 |
| TimescaleDB  | Time-series measurements and historical trends                |
| Qdrant       | Semantic memory and knowledge retrieval                       |
| Neo4j        | Graph relationships, memory chains, social graph, claim graph |
| Object Store | Documents, reports, PDFs, attachments                         |

---

### 5.7 Plane 7: Infrastructure

**Purpose:** Provide secure, observable, scalable runtime foundations.

**Primary Components:**

- Encryption service.
- Key management service.
- Circuit breakers.
- Retry policies.
- Provider failover.
- Distributed tracing.
- Metrics and dashboards.
- Audit log pipeline.
- Background workers.
- Secret management.
- Deployment and release orchestration.

---

## 6. Request Lifecycle

### 6.1 Synchronous Request Flow

```text
Client
  -> Edge Gateway
  -> RequestContextMiddleware
  -> TenantContextMiddleware
  -> RuntimeContextMiddleware
  -> Auth + Rate Limit + Idempotency
  -> ButlerEnvelope construction
  -> ExecutionOrchestrator
  -> IntakeProcessor
  -> ContentGuard + Redaction
  -> Complexity + Intent Classification
  -> CostRouter
  -> PlanEngine
  -> ContextSelector
  -> RuntimeKernel
  -> Agent/Tool/LLM Execution
  -> OutputValidator
  -> Response Envelope
  -> Audit + Metrics
  -> Client
```

### 6.2 Async Workflow Flow

```text
Client
  -> Gateway
  -> Orchestrator creates Workflow
  -> Queue dispatch
  -> Worker resumes Workflow
  -> ContextSelector rebuilds allowed context
  -> RuntimeKernel executes next step
  -> Checkpoint written
  -> Notification or pollable result emitted
```

### 6.3 Canonical Request Envelope

```python
class ButlerEnvelope(BaseModel):
    request_id: UUID
    tenant_id: UUID
    user_id: UUID
    session_id: UUID | None
    idempotency_key: str | None
    channel: Literal["web", "mobile", "voice", "api", "worker"]
    locale: str
    timezone: str
    user_input: str
    attachments: list[AttachmentRef]
    auth_context: AuthContext
    runtime_context: RuntimeContext
    policy_context: PolicyContext
    created_at: datetime
```

### 6.4 Canonical Response Envelope

```python
class OrchestratorResult(BaseModel):
    request_id: UUID
    workflow_id: UUID | None
    status: Literal["completed", "partial", "needs_approval", "failed", "queued"]
    response_text: str | None
    structured_output: dict[str, Any] | None
    citations: list[SourceCitation]
    actions: list[ProposedAction]
    audit_ref: str
    usage: RuntimeUsage
    errors: list[ExecutionError]
```

---

## 7. Execution Lanes

### 7.1 Lane Table

| Complexity | Lane               | Runtime                   | Typical Use                                            | Approval Needed |
| ---------: | ------------------ | ------------------------- | ------------------------------------------------------ | --------------- |
|          1 | Deterministic Tool | No LLM or nano model      | Format, lookup, simple operation                       | No              |
|          2 | LLM Answer         | Cheap model               | Simple Q&A, rewrite, summary                           | No              |
|          3 | LLM With Tools     | Tool-capable model        | Search, retrieve, calculate, inspect docs              | Sometimes       |
|          4 | Domain Crew        | Multi-step bounded agents | Planning, analysis, multi-domain but bridge-safe tasks | Often           |
|          5 | Async Crew         | Durable workflow          | Long research, batch processing, scheduled work        | Often           |

### 7.2 Complexity Classifier

The complexity classifier is a lightweight model or policy-driven classifier selected by tenant configuration. It must output:

```python
class ComplexityDecision(BaseModel):
    score: float  # 1.0 to 5.0
    lane: ExecutionLane
    confidence: float
    signals: list[ComplexitySignal]
    escalation_reason: str | None
```

Recommended signals:

- Input length and structure.
- Entity count.
- Temporal ambiguity.
- Tool dependency hints.
- Domain count.
- Sensitivity class.
- Historical complexity for this tenant.
- Semantic distance from deterministic cached answers.

### 7.3 Escalation Rules

Escalation is allowed when:

- The selected lane cannot satisfy required tools.
- The answer requires private domain context.
- The task includes high-risk external actions.
- The confidence score falls below configured threshold.
- The output validator rejects the response and retry budget remains.

Escalation is forbidden when:

- Tenant budget is exceeded.
- Policy denies requested action.
- The request requires unauthorized domain access.
- The user has not approved a required high-impact action.

---

## 8. Domain Architecture

### 8.1 Domain Ownership Model

Each domain owns:

- Raw records.
- Domain schemas.
- Domain services.
- Domain events.
- Summary projection interface.
- Access policy.
- Storage adapter interfaces.
- Domain-specific agents.

Each domain exposes only:

- Public command APIs.
- Public query APIs.
- Summary projection APIs.
- Domain event streams.
- Bridge-approved payloads.

---

### 8.2 Domain Registry

| Domain        | Owns                                                                  | May Emit                                       | May Read                                            |
| ------------- | --------------------------------------------------------------------- | ---------------------------------------------- | --------------------------------------------------- |
| Finance       | Accounts, transactions, budgets, goals, net worth                     | Financial events, finance summary              | Finance raw data only                               |
| Health        | Conditions, medications, appointments, vitals, fitness, mental health | Health events, health status summary           | Health raw data only                                |
| Projects      | Projects, tasks, milestones, decisions, notes                         | Professional events, project summary           | Project raw data, approved Social names             |
| Social Graph  | Persons, groups, relationships, interactions                          | Relationship events, social summary, team refs | Social raw data only                                |
| History Graph | Memory nodes, life chapters, memory chains                            | Major life markers                             | Domain event payloads, user-invoked history queries |
| Digital Twin  | Computed user state                                                   | TwinContext                                    | Domain summaries only                               |
| Knowledge     | Claims, sources, technical notes, embeddings                          | Knowledge citations, retrieval packets         | Knowledge store only                                |

---

### 8.3 Finance Domain

**Responsibility**

Manage personal financial records, computed financial state, financial goals, recurring obligations, cashflow forecasts, and finance-specific alerts.

**Core Aggregates**

- `Account`.
- `Transaction`.
- `Budget`.
- `FinancialGoal`.
- `RecurringCharge`.
- `DebtInstrument`.
- `InvestmentPosition`.
- `NetWorthSnapshot`.

**Agents**

| Agent          | Responsibility                                                     |
| -------------- | ------------------------------------------------------------------ |
| FinanceScout   | Ingest transactions, classify merchants, detect recurring patterns |
| FinancePlanner | Budget analysis, goal progress, scenario modeling                  |
| FinanceAlert   | Due reminders, threshold alerts, anomaly notifications             |

**Bridge Outputs**

- `FinanceSummaryForTwin`.
- `FinancialMilestoneEvent`.
- `FinancialCrisisUserTaggedEvent`.

**Forbidden Outputs**

- Raw transaction amounts to History Graph.
- Account balances to Digital Twin.
- Health inference from medical spending.

---

### 8.4 Health Domain

**Responsibility**

Manage health records, medications, appointments, vitals, fitness, insurance-related health documents, and mental health data under strict encryption.

**Core Aggregates**

- `MedicalCondition`.
- `Medication`.
- `HealthAppointment`.
- `VitalSignEntry`.
- `FitnessEntry`.
- `MentalHealthEntry`.
- `HealthDocument`.
- `VaccinationRecord`.

**Agents**

| Agent                | Responsibility                                              |
| -------------------- | ----------------------------------------------------------- |
| HealthScout          | Device/app ingestion, OCR extraction, refill tracking       |
| HealthAnalyst        | Trend analysis, correlation discovery, adherence tracking   |
| HealthCoordinator    | Appointment prep, referral follow-up, reminder coordination |
| MentalHealthGuardian | Isolated mental health monitoring and supportive reflection |

**Bridge Outputs**

- `HealthStatusForTwin`: status-only summary.
- `HealthMilestoneEvent`: no clinical detail.
- `MentalHealthMilestoneEvent`: only when explicitly approved by policy and user settings.

**Forbidden Outputs**

- Lab values to Digital Twin.
- Medication names to History Graph.
- Mental health entries to non-health agents.
- Health-derived work/productivity recommendations inside Project domain.

---

### 8.5 Project Domain

**Responsibility**

Manage professional, learning, research, coding, and personal project execution without reading personal finance or health data.

**Core Aggregates**

- `Project`.
- `Task`.
- `Milestone`.
- `ProjectDecision`.
- `ProjectNote`.
- `TeamMemberRef`.
- `LearningModule`.
- `ResearchArtifact`.

**Agents**

| Agent           | Responsibility                                           |
| --------------- | -------------------------------------------------------- |
| ProjectPlanner  | Decomposition, estimates, milestones, dependency mapping |
| ProjectMonitor  | Velocity, blockers, deadline risk                        |
| ProjectBriefing | Daily/weekly briefings, meeting prep, retrospectives     |
| LearningPlanner | Curriculum planning, spaced repetition, assessments      |
| ResearchScout   | Literature review, source extraction, claim tracking     |

**Bridge Outputs**

- `ProjectSummaryForTwin`.
- `ProfessionalMilestoneEvent`.
- `SkillAcquiredEvent`.

**Bridge Inputs**

- `TeamMemberDisplayRef` from Social Graph only.

**Forbidden Inputs**

- Health status.
- Financial pressure.
- Relationship context unrelated to team references.
- Full Digital Twin context.

---

### 8.6 Social Graph Domain

**Responsibility**

Manage the user's personal memory of people, groups, relationships, interaction history, important dates, and relationship context.

**Core Aggregates**

- `Person`.
- `Relationship`.
- `Group`.
- `InteractionLog`.
- `ImportantDate`.
- `ConsentRecord`.

**Agents**

| Agent              | Responsibility                                               |
| ------------------ | ------------------------------------------------------------ |
| RelationshipScout  | Important dates, silence detection, context surfacing        |
| GroupCoordinator   | Group planning, gift/context suggestions, dynamics awareness |
| RelationshipMemory | Person-specific memory retrieval                             |

**Bridge Outputs**

- `SocialSummaryForTwin`.
- `RelationshipMilestoneEvent`.
- `TeamMemberDisplayRef` to Project domain.

**Consent Rule**

Social Graph stores the user's memory of other people. It must not be treated as externally shareable data about those people without explicit consent.

---

### 8.7 History Graph Domain

**Responsibility**

Maintain a temporal personal knowledge graph of major life events, memory nodes, life chapters, causal chains, and user-authored memories.

**Core Aggregates**

- `MemoryNode`.
- `LifeChapter`.
- `MemoryChain`.
- `MemoryAttribution`.
- `TimelineProjection`.

**Agents**

| Agent               | Responsibility                                                  |
| ------------------- | --------------------------------------------------------------- |
| HistoryScout        | Timeline views, filtered memory retrieval, chain suggestions    |
| HistoryAnalyst      | Pattern analysis, life chapter analysis, longitudinal summaries |
| AttributionEnforcer | Ensures every memory query specifies subject attribution        |

**Read Rule**

History Graph is not part of default agent context. It is read only when explicitly invoked by the user or by a policy-approved workflow.

**Sealed Memory Rule**

Sealed memories are never surfaced in AI context under any circumstance.

---

### 8.8 Digital Twin Domain

**Responsibility**

Maintain a computed, versioned, summary-only model of the user's current state.

The Digital Twin is not a source of truth. It is a projection built from domain summaries.

**Core Structures**

- `TwinIdentity`.
- `TwinLifeContext`.
- `TwinPriority`.
- `TwinAttentionFlag`.
- `TwinBehaviorProfile`.
- `TwinGoalSummary`.
- `TwinVersion`.

**Update Flow**

```text
Domain Event
  -> Event Bus
  -> TwinUpdater Worker
  -> Domain Summary Interfaces
  -> Bridge Validation
  -> Twin Projection Recompute
  -> Twin Version Append
```

**TwinContext Injection**

Agents receive only a lightweight `TwinContext`:

```python
class TwinContext(BaseModel):
    preferred_name: str
    timezone: str
    communication_style: str
    decision_style: str
    current_life_phase: str | None
    top_priorities: list[TwinPrioritySummary]
    active_attention_flags: list[TwinAttentionFlagSummary]
    behavioral_hints: list[str]
```

Project agents do not receive full `TwinContext` by default.

---

## 9. Cross-Domain Bridge

### 9.1 Purpose

The Cross-Domain Bridge is the only approved mechanism for inter-domain data flow.

All bridge payloads must be:

- Explicitly registered.
- Schema validated.
- Source-target validated.
- Data classification validated.
- Audited.
- Versioned.

### 9.2 Bridge Registry

```python
class BridgeRule(BaseModel):
    source_domain: DomainName
    target_domain: DomainName
    payload_type: str
    schema_version: str
    max_data_tier: DataTier
    allowed_fields: set[str]
    denied_fields: set[str]
    requires_user_approval: bool
    retention_policy: RetentionPolicy
```

### 9.3 Approved Bridge Matrix

| Source        | Target        | Payload                      | Allowed                           | Forbidden                              |
| ------------- | ------------- | ---------------------------- | --------------------------------- | -------------------------------------- |
| Finance       | Digital Twin  | `FinanceSummaryForTwin`      | phase, goal progress %, alerts    | amounts, balances, account IDs         |
| Finance       | History Graph | `FinancialMilestoneEvent`    | event type, category, date        | transaction details, balances          |
| Health        | Digital Twin  | `HealthStatusForTwin`        | one-word status, attention flag   | diagnoses, meds, lab values            |
| Health        | History Graph | `HealthMilestoneEvent`       | milestone type, date, sentiment   | clinical detail, scores                |
| Projects      | Digital Twin  | `ProjectSummaryForTwin`      | counts, progress %, overdue count | team details, private project text     |
| Projects      | History Graph | `ProfessionalMilestoneEvent` | title, date, user tags            | task internals, private notes          |
| Social        | Digital Twin  | `SocialSummaryForTwin`       | counts, upcoming-date counts      | names, contact info                    |
| Social        | Projects      | `TeamMemberDisplayRef`       | display name, role hint           | relationship history, contact detail   |
| Social        | History Graph | `RelationshipMilestoneEvent` | event type, date                  | private interaction logs               |
| History Graph | Digital Twin  | `LifeEventMarker`            | major event type, date            | memory body, clinical/financial detail |

### 9.4 Violation Handling

```python
class CrossDomainViolation(SecurityException):
    source_domain: str
    target_domain: str
    payload_type: str
    denied_fields: list[str]
    request_id: UUID
    tenant_id: UUID
```

On violation:

1. Reject operation.
2. Emit critical audit event.
3. Increment security metric.
4. Notify security pipeline if severity threshold is met.
5. Prevent retry without policy change.

---

## 10. Encryption and Data Classification

### 10.1 Data Tiers

| Tier    | Meaning                                      | Examples                                                        | Server Plaintext Allowed?               |
| ------- | -------------------------------------------- | --------------------------------------------------------------- | --------------------------------------- |
| Tier A  | End-to-end encrypted personal data           | health records, finance amounts, contact details, memory bodies | Only during controlled execution window |
| Tier A+ | Extra-protected data                         | mental health entries, sealed memories                          | Only explicit mode and sub-key access   |
| Tier B  | Server-encrypted operational/domain metadata | project metadata, embeddings, tool metadata                     | Yes, under service policy               |
| Tier C  | Non-sensitive telemetry                      | request IDs, route decisions, latency, cost                     | Yes                                     |

### 10.2 Key Model

```text
User Device
  -> User Master Key generated locally
  -> Session Key created per session
  -> Session Key encrypted by User Master Key
  -> Server receives encrypted session key and encrypted payloads
```

The server never receives the User Master Key.

### 10.3 Decryption Boundary

Only `ContextDecryptionBoundary` may decrypt Tier A or Tier A+ data.

Rules:

- Decrypt minimum required records only.
- Use short-lived memory scope.
- Never log plaintext.
- Never cache plaintext.
- Never persist plaintext.
- Never pass plaintext into metrics.
- Wipe or isolate memory after execution.

### 10.4 Secure Wipe Note

Python string deletion is not reliable secure wiping. Production implementations must use one of:

1. Rust/C extension for plaintext buffers.
2. Dedicated subprocess that exits after execution.
3. OS-backed confidential memory where supported.
4. Strict minimization plus zero plaintext persistence when hard wipe cannot be guaranteed.

---

## 11. Tool Execution Architecture

### 11.1 Tool Flow

```text
Agent proposes tool call
  -> ToolRegistry.get_spec()
  -> ToolPolicy.evaluate()
  -> ApprovalService if required
  -> OperationRouter.route()
  -> Quota + admission control
  -> SandboxManager.execute()
  -> Tool result validation
  -> Result redaction
  -> Agent receives sanitized result
```

### 11.2 Tool Specification

```python
class ToolSpec(BaseModel):
    name: str
    version: str
    domain: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_tier: RiskTier
    auth_mode: ToolAuthMode
    allowed_agents: list[str]
    required_scopes: list[str]
    timeout_ms: int
    idempotent: bool
```

### 11.3 Tool Policy Decision

```python
class ToolPolicyDecision(BaseModel):
    allowed: bool
    requires_approval: bool
    risk_tier: RiskTier
    reason: str
    sandbox_profile: str
    max_runtime_ms: int
    allowed_network_hosts: list[str]
```

### 11.4 Risk Tiers

| Tier | Description                      | Examples                                             | Default Approval             |
| ---- | -------------------------------- | ---------------------------------------------------- | ---------------------------- |
| R0   | Read-only safe                   | fetch own note, summarize local file                 | No                           |
| R1   | Low-risk reversible              | create draft, add reminder                           | No or configurable           |
| R2   | External visible                 | send email draft for approval, create calendar event | Yes                          |
| R3   | Financial/account-changing       | payment, purchase, account update                    | Yes, strong confirmation     |
| R4   | Health/legal/emergency-sensitive | medical action, legal filing, emergency instructions | Yes, explicit and restricted |

---

## 12. Agent Runtime

### 12.1 Backend Selection

Runtime backend is selected through configuration, not hardcoded branching.

Example:

```text
BUTLER_AGENT_RUNTIME=langgraph | hermes_legacy | deterministic | remote_worker
```

The selected backend must implement:

```python
class AgentBackend(Protocol):
    async def execute(self, context: ExecutionContext) -> AgentExecutionResult:
        ...
```

### 12.2 LangGraph Runtime Pattern

```text
ButlerChatModel
  -> wraps MLRuntimeManager
ButlerToolFactory
  -> converts ToolSpec into model-bindable tools
StateGraph
  -> executes planned agent state transitions
RuntimeKernel
  -> owns lifecycle, retries, finalization
```

### 12.3 Legacy Runtime Pattern

Legacy runtimes may remain behind adapters while migration occurs. They must not bypass:

- ToolPolicy.
- OperationRouter.
- SandboxManager.
- ContextDecryptionBoundary.
- OutputValidator.
- Audit logging.

---

## 13. Prompt and Configuration System

### 13.1 Prompt Hub

Prompts are versioned configuration artifacts, not hardcoded strings.

Prompt resolution order:

```text
system baseline
  -> tenant policy overlay
  -> domain prompt
  -> agent role prompt
  -> task prompt
  -> runtime safety constraints
```

### 13.2 Prompt Artifact Schema

```yaml
id: finance.planner.v1
version: 1.0.0
domain: finance
agent: FinancePlanner
allowed_tools:
  - finance.read_budget
  - finance.simulate_cashflow
forbidden_context:
  - health.raw
  - social.raw
output_schema: FinancePlanOutput
safety_policy: finance_advice_standard
```

### 13.3 No-Hardcoding Rule

The following must be configurable:

- Model names.
- Provider priority.
- Tool registry entries.
- Prompt templates.
- Complexity thresholds.
- Retry budgets.
- Context budgets.
- Risk policy.
- Tenant cost budgets.
- Domain bridge rules.

---

## 14. Memory and Knowledge Architecture

### 14.1 Memory Types

| Memory Type     | Store                             | Description                               |
| --------------- | --------------------------------- | ----------------------------------------- |
| Session memory  | Redis/PostgreSQL                  | Current conversation and short-term state |
| Episodic memory | PostgreSQL/Qdrant                 | User events and remembered interactions   |
| Semantic memory | Qdrant                            | Embedding-based retrieval                 |
| Graph memory    | Neo4j                             | Entities, relationships, causal chains    |
| Domain memory   | Domain stores                     | Finance, health, project, social records  |
| Sealed memory   | Encrypted object store + metadata | Never included in AI context              |

### 14.2 Context Retrieval Pipeline

```text
Request intent
  -> allowed scopes from policy
  -> parallel retrieval
  -> context sanitizer
  -> source ranking
  -> duplication removal
  -> budget compaction
  -> decryption boundary
  -> execution context
```

### 14.3 Reflexion Write Policy

Reflexion output may be stored only if:

- It is based on verified execution results.
- It is not derived from adversarial tool output without sanitization.
- It includes source attribution.
- It passes memory write policy.
- It does not violate domain walls.
- It does not store private deliberation as fact.

---

## 15. Storage Architecture

### 15.1 Finance Storage

| Data                 | Store                    | Encryption                        |
| -------------------- | ------------------------ | --------------------------------- |
| Accounts             | PostgreSQL               | Tier A for balances/details       |
| Transactions         | PostgreSQL + TimescaleDB | Tier A for amount/raw description |
| Budgets/goals        | PostgreSQL               | Tier A/Tier B mixed               |
| Net worth snapshots  | TimescaleDB              | Tier A                            |
| Current budget cache | Redis                    | Encrypted or metadata-only        |

### 15.2 Health Storage

| Data                   | Store                   | Encryption                |
| ---------------------- | ----------------------- | ------------------------- |
| Conditions/medications | PostgreSQL              | Tier A                    |
| Vitals/fitness         | TimescaleDB             | Tier A                    |
| Mental health entries  | PostgreSQL/Object Store | Tier A+                   |
| Medical documents      | Object Store            | Tier A                    |
| Reminders              | Redis/PostgreSQL        | Tier A metadata-minimized |

### 15.3 Project Storage

| Data                | Store        | Encryption                           |
| ------------------- | ------------ | ------------------------------------ |
| Projects/tasks      | PostgreSQL   | Tier B or tenant-configurable Tier A |
| Decisions/notes     | PostgreSQL   | Tier B/Tier A if private             |
| Active status cache | Redis        | Tier B                               |
| Attachments         | Object Store | Configurable                         |

### 15.4 Social Graph Storage

| Data             | Store            | Encryption                              |
| ---------------- | ---------------- | --------------------------------------- |
| Person nodes     | Neo4j/PostgreSQL | Tier B metadata, Tier A contact details |
| Relationships    | Neo4j            | Tier B/Tier A depending field           |
| Interaction logs | PostgreSQL       | Tier A for summaries                    |
| Important dates  | PostgreSQL/Redis | Tier B unless sensitive                 |

### 15.5 History Graph Storage

| Data              | Store            | Encryption                           |
| ----------------- | ---------------- | ------------------------------------ |
| Memory nodes      | Neo4j/PostgreSQL | Tier A body, Tier B metadata         |
| Memory embeddings | Qdrant           | Derived and encrypted where required |
| Memory chains     | Neo4j            | Tier B metadata, Tier A details      |
| Sealed memories   | Object Store     | Tier A+                              |

---

## 16. Observability and Audit

### 16.1 Metrics

Minimum metrics:

- `request.count` by tenant, lane, status.
- `request.latency_ms` by plane and lane.
- `model.tokens.input/output`.
- `model.cost` by provider and tenant.
- `tool.execution.count` by tool and risk tier.
- `tool.execution.failure_rate`.
- `policy.denial.count`.
- `cross_domain_violation.count`.
- `context.retrieval.latency_ms`.
- `context.sanitizer.findings.count`.
- `approval.required.count`.
- `approval.accepted/rejected.count`.

### 16.2 Tracing

Every request trace must include:

- `request_id`.
- `tenant_id`.
- `user_id_hash`.
- `workflow_id` if present.
- `lane`.
- `agent_backend`.
- `model_provider`.
- `tool_names`.
- `policy_decision_ids`.
- `audit_ref`.

No sensitive plaintext is allowed in traces.

### 16.3 Audit Events

Audit all:

- Authentication failures.
- Policy denials.
- Cross-domain violations.
- Tool executions.
- Approval decisions.
- Decryption boundary access.
- Memory writes.
- Domain bridge emissions.
- Provider failovers.
- Admin configuration changes.

---

## 17. Reliability Model

### 17.1 Failure Classes

| Class              | Example                     | Expected Handling                        |
| ------------------ | --------------------------- | ---------------------------------------- |
| Provider failure   | LLM timeout                 | Retry/failover if policy permits         |
| Tool failure       | Browser crash               | Retry bounded, return partial result     |
| Policy denial      | Tool not allowed            | Stop and explain safe alternative        |
| Bridge violation   | Health raw data to Projects | Raise security error, audit critical     |
| Context overload   | Token budget exceeded       | Compact, rank, or ask for narrower scope |
| Decryption failure | Key unavailable             | Stop, request re-auth/session renewal    |
| Validation failure | Output schema mismatch      | Retry with correction if budget remains  |

### 17.2 Circuit Breakers

Circuit breakers must exist for:

- Model providers.
- Tool providers.
- External APIs.
- Vector database.
- Graph database.
- Encryption service.
- Queue workers.

### 17.3 Idempotency

Every externally visible action must support idempotency. The idempotency key must bind:

- Tenant.
- User.
- Tool/action.
- Input hash.
- Approval ID if required.

---

## 18. Security Requirements

### 18.1 Mandatory Controls

- Tenant isolation at API, storage, cache, queue, and key layers.
- Per-tool scope enforcement.
- Per-agent allowed tool list.
- Context sanitizer before model use.
- Prompt injection detection for retrieved content.
- Output validation before response/action.
- Approval service for R2+ actions.
- Audit log immutability.
- Secrets outside application config.
- Principle of least privilege for service accounts.

### 18.2 Threats to Test

- Cross-domain data exfiltration.
- Prompt injection from documents/web pages/tool results.
- Tool hijacking through retrieved content.
- Malicious memory poisoning.
- Tenant boundary bypass.
- Replay of approved actions.
- Logging of decrypted data.
- Unauthorized backend runtime selection.
- Provider fallback to weaker policy environment.

---

## 19. API Surface

### 19.1 Core Runtime APIs

| Endpoint                 | Method | Purpose                       |
| ------------------------ | ------ | ----------------------------- |
| `/api/v1/chat`           | POST   | Synchronous user request      |
| `/api/v1/workflows`      | POST   | Create long-running workflow  |
| `/api/v1/workflows/{id}` | GET    | Read workflow status/result   |
| `/api/v1/approvals`      | GET    | List pending approvals        |
| `/api/v1/approvals/{id}` | POST   | Accept/reject approval        |
| `/api/v1/tools`          | GET    | List available tools by scope |
| `/api/v1/twin/context`   | GET    | Read lightweight TwinContext  |
| `/api/v1/memory/search`  | POST   | User-invoked memory search    |

### 19.2 Domain APIs

Domain APIs should follow command/query separation:

```text
POST /api/v1/finance/commands/import-transactions
GET  /api/v1/finance/queries/budget-summary
POST /api/v1/health/commands/add-medication
GET  /api/v1/projects/queries/daily-briefing
POST /api/v1/social/commands/log-interaction
POST /api/v1/history/queries/timeline
```

---

## 20. Dependency Injection Pattern

Runtime wiring should be centralized and explicit.

```python
async def get_orchestrator_service() -> OrchestratorService:
    memory = get_memory_service()
    tools = get_tools_service()
    blender = get_butler_blender()
    router = get_smart_router()
    backend = get_agent_backend(settings.BUTLER_AGENT_RUNTIME)
    kernel = RuntimeKernel(
        memory_service=memory,
        tools_service=tools,
        router=router,
        agent_backend=backend,
    )
    return OrchestratorService(
        memory_service=memory,
        tools_service=tools,
        blender=blender,
        router=router,
        runtime_kernel=kernel,
    )
```

Rules:

- No hidden global service lookups inside domain logic.
- No model/provider clients inside domain entities.
- No direct database access from API route handlers.
- Runtime dependencies are injected through interfaces.

---

## 21. Implementation Phases

### Phase 0: Architecture Hardening

Deliverables:

- Domain boundary map.
- Bridge registry.
- Data classification registry.
- Execution lane registry.
- Tool risk model.
- Prompt registry.
- Observability baseline.

Exit Criteria:

- Cross-domain violation tests fail closed.
- No API route contains business logic.
- No domain imports infrastructure/framework modules.

### Phase 1: Runtime Foundation

Deliverables:

- Gateway envelope flow.
- Middleware chain.
- Orchestrator intake.
- Complexity classifier interface.
- CostRouter.
- RuntimeKernel.
- Deterministic and LLM answer lanes.

Exit Criteria:

- Complexity 1/2 requests complete through configured lanes.
- Per-tenant rate limits and budgets enforced.
- Basic traces and audit logs emitted.

### Phase 2: Tool and Agent Runtime

Deliverables:

- ToolRegistry.
- ToolPolicy.
- OperationRouter.
- SandboxManager.
- LangGraph backend adapter.
- Legacy backend adapter boundary.
- OutputValidator.

Exit Criteria:

- Agents cannot execute unregistered tools.
- R2+ actions require approval.
- Tool results are sanitized before model re-entry.

### Phase 3: Context and Memory

Deliverables:

- ContextSelector.
- ContextBudgetManager.
- ContextSanitizer.
- ContextDecryptionBoundary.
- Memory write policy.
- Retrieval source attribution.

Exit Criteria:

- No decrypted data appears in logs/traces.
- Memory writes require source attribution and policy approval.
- Prompt injection test corpus passes.

### Phase 4: Domain Implementation

Deliverables:

- Finance domain.
- Health domain with mental health sub-domain.
- Project domain.
- Social Graph domain.
- History Graph domain.
- Digital Twin projection.

Exit Criteria:

- Each domain exposes summary and event interfaces only.
- Bridge payloads validate against registry.
- Project domain cannot access personal domains.

### Phase 5: Crew and Async Workflows

Deliverables:

- DomainCrew runtime.
- Gate rejection loop.
- Workflow checkpointing.
- Async queue workers.
- Notification bridge.

Exit Criteria:

- Complexity 4/5 workflows are resumable.
- Gate rejection produces structured deltas.
- Retry budgets are enforced.

### Phase 6: Production Readiness

Deliverables:

- SLO dashboards.
- Security threat tests.
- Load tests.
- Cost tests.
- Disaster recovery runbooks.
- Key rotation runbook.
- Incident response playbook.

Exit Criteria:

- P95 targets are met for lanes 1-3.
- Cross-domain security tests pass.
- Tenant isolation tests pass.
- Provider failure drills pass.

---

## 22. Testing Strategy

### 22.1 Test Categories

| Category    | Required Tests                                              |
| ----------- | ----------------------------------------------------------- |
| Unit        | Domain services, value objects, policies                    |
| Contract    | Bridge payloads, tool schemas, agent outputs                |
| Integration | Orchestrator, memory, tool execution, provider adapters     |
| Security    | Tenant isolation, prompt injection, cross-domain violations |
| Load        | Gateway, retrieval, workflow queue, storage                 |
| Chaos       | Provider outage, queue delay, Redis failure, DB failover    |
| Privacy     | No plaintext logs, decryption boundary enforcement          |

### 22.2 Mandatory Boundary Tests

- Finance raw amount cannot enter Digital Twin.
- Health diagnosis cannot enter Project domain.
- Mental health entry cannot enter generic agent context.
- Project agent cannot read TwinContext unless explicitly configured.
- History Graph cannot expose sealed memory.
- Tool output prompt injection cannot alter system/tool policy.
- Agent cannot call tool outside allowed scope.

---

## 23. SLO Targets

| Component                        | Target                                   |
| -------------------------------- | ---------------------------------------- |
| Gateway ingress                  | P95 < 30 ms                              |
| Control plane routing            | P95 < 50 ms                              |
| Context retrieval                | P95 < 200 ms                             |
| Complexity 1/2 response          | P95 < 800 ms excluding provider variance |
| Complexity 3 response            | P95 < 2.5 s excluding external tools     |
| Complexity 4/5 sync response     | P95 < 5 s for bounded tasks              |
| Workflow enqueue                 | P95 < 150 ms                             |
| Audit log write                  | P99 < 100 ms                             |
| Cross-domain violation detection | 100% fail closed                         |

---

## 24. Open Engineering Decisions

| Decision              | Options                                       | Recommendation                                                         |
| --------------------- | --------------------------------------------- | ---------------------------------------------------------------------- |
| Decryption runtime    | Python boundary, Rust extension, subprocess   | Use subprocess/Rust for Tier A+                                        |
| Complexity classifier | Rules, small model, hybrid                    | Hybrid with model-backed classifier                                    |
| Graph DB              | Neo4j, Memgraph, Postgres graph extensions    | Neo4j initially, abstract behind repository                            |
| Vector store          | Qdrant, pgvector, Milvus                      | Qdrant for memory search, pgvector acceptable for small deployments    |
| Workflow engine       | LangGraph checkpoints, Temporal, custom queue | LangGraph for agent state, Temporal/Celery for durable infra workflows |
| Prompt registry       | DB, files, config service                     | Versioned DB/config service with file fallback                         |
| Tool sandbox          | Docker, Firecracker, provider-native sandbox  | Docker for dev, Firecracker/gVisor for production high-risk tools      |

---

## 25. Acceptance Criteria

BIS v2 architecture is implementation-ready only when:

1. Every domain has a bounded context document.
2. Every cross-domain payload is registered and schema validated.
3. Every execution lane has explicit routing criteria.
4. Every agent has a role, scope, tools, memory access, budget, and output schema.
5. Every tool has policy, risk tier, sandbox profile, and approval behavior.
6. Every sensitive field has a data tier and encryption rule.
7. Every request emits trace and audit metadata without sensitive plaintext.
8. Every high-risk action requires approval.
9. Every provider dependency is behind an interface.
10. Every domain boundary has automated tests proving fail-closed behavior.

---

## 26. Summary

BIS v2 is a governed personal intelligence runtime, not a single assistant prompt. The architecture depends on strict domain ownership, bridge-only data movement, computational gravity, policy-gated tools, encrypted memory, and observable execution.

The system should be built contract-first:

1. Define domain boundaries.
2. Define bridge payloads.
3. Define execution lanes.
4. Define tool policies.
5. Define memory and encryption rules.
6. Implement runtime adapters behind interfaces.
7. Add agents only after the runtime can enforce safety.

The highest-risk mistake is building agent features before boundary enforcement. The correct build order is infrastructure, contracts, policies, runtime, then agents.

---

# 0. Architectural Corrections (Critical Context)

**Before a single line of code, every engineer must understand these corrections.** The original document contains architectural aspirations. This plan contains executable reality.

## Gap 1: Complexity Scoring Is Undefined

**Problem**: The document says "Complexity 1/2 → cheap lane" but never explains HOW complexity is measured.  
**Fix**: Complexity scoring is a trained lightweight classifier (Gemma 4 Edge, 7B param), NOT a rule engine. It scores on 6 signals:
- Token count of input
- Number of distinct entities (NER pass)
- Presence of temporal ambiguity
- Tool dependency hints in query
- Historical task complexity for this tenant
- Semantic distance from deterministic cache hits

Output: float 1.0–5.0. This classifier IS the Nano-Gatekeeper's primary function and must be trained and validated BEFORE Phase 2 begins.

## Gap 2: Council Engine Has Zero Design

**Problem**: "Multi-model consensus" appears in the mode table but has no implementation anywhere.  
**Fix**: Council Engine = 3-model jury with structured debate protocol.
- Model A (Claude Sonnet): Base reasoning
- Model B (GPT-4o / Gemini Pro): Independent reasoning
- Model C (specialized domain model): Domain expertise
- Each produces answer + confidence + reasoning chain
- Council Arbiter: Embedding similarity vote + confidence weighting
- Tie-breaker: Gate Agent validation on disputed claims
- Consensus threshold: 0.80 cosine similarity between top-2 answers

## Gap 3: Secure Wipe Is Fake in Python

**Problem**: `del decrypted; secure_wipe(decrypted)` does nothing meaningful in CPython.  
**Fix**: Plaintext handling must use `ctypes` memory zeroing OR offload to a Rust/C extension.
```python
import ctypes

def secure_wipe(data: str) -> None:
    """Actually wipe string from CPython memory."""
    encoded = data.encode('utf-8')
    buf = (ctypes.c_char * len(encoded)).from_buffer(bytearray(encoded))
    ctypes.memset(buf, 0, len(encoded))
    del data, encoded, buf
```
Alternative: Run all decryption in a subprocess that exits after use (memory reclaimed by OS on exit). This is the more reliable option for production.

## Gap 4: Loop Logic in Gate → Run Is Undefined

**Problem**: When Gate rejects Run's output, the document says "loop" but defines no loop semantics.  
**Fix**: Gate rejection must produce a structured `RejectionDelta`:
```python
class RejectionDelta(BaseModel):
    rejected_claim: str
    violation_type: str  # constraint|quality|safety|factual
    suggested_correction: Optional[str]
    retry_allowed: bool
```

## Gap 5: Reflexion Poisoning Is Unaddressed

**Problem**: Agents can be poisoned by adversarial context in memory retrieval.  
**Fix**: All context retrieval must pass through a `ContextSanitizer` that:
- Detects prompt injection patterns in retrieved context
- Scores context relevance (drop below threshold)
- Detects contradictory statements in retrieved context
- Flags context from untrusted sources for special handling

## Gap 6: 10K RPS Scaling Is Unsupported

**Problem**: Document claims 10K RPS target but provides no scaling strategy.  
**Fix**: Scaling requirements for 10K RPS:
- Connection pooling: 200+ DB connections per instance
- Redis clustering: 3+ shards with read replicas
- Model provider load balancing: Round-robin with quota-aware failover
- Horizontal pod autoscaling: CPU-based (70% target) with custom metrics for queue depth
- Caching: Multi-tier (L1: in-memory, L2: Redis, L3: CDN for static content)
- Rate limiting per tenant: Token bucket with burst capacity
- Circuit breakers: Per-provider with exponential backoff

Run agent receives the delta and generates a targeted correction, not a full re-run. Max 3 retries before Sync escalates to higher lane. This is enforced by TaskLedger tracking `GATE_REJECTION` count.

## Gap 5: Reflexion Poisoning Is Unaddressed

**Problem**: Bad lessons from bad task completions get stored as valid episodic memory.  
**Fix**: Reflexion writes are NEVER immediate. All new AgentMemoryNodes enter a `PENDING` state. They are promoted to `ACTIVE` only after:
- Gate Agent validation (automated)
- Contradiction check against existing graph
- User implicit feedback (task follow-up didn't contradict)
- Time threshold (48 hours minimum, configurable)

## Gap 6: 10K RPS Scaling Is Unsupported

**Problem**: Document claims 10K RPS target but provides no scaling strategy.  
**Fix**: Scaling requirements for 10K RPS:
- Connection pooling: 200+ DB connections per instance
- Redis clustering: 3+ shards with read replicas
- Model provider load balancing: Round-robin with quota-aware failover
- Horizontal pod autoscaling: CPU-based (70% target) with custom metrics for queue depth
- Caching: Multi-tier (L1: in-memory, L2: Redis, L3: CDN for static content)
- Rate limiting per tenant: Token bucket with burst capacity
- Circuit breakers: Per-provider with exponential backoff

## Gap 7: Current Implementation Details Not Integrated

**Problem**: The BIS v2 plan does not reflect the actual current implementation in the Butler backend.  
**Fix**: Integrate current implementation details from Butler Backend Execution Flow Map:

**Current Implementation State** (from codemap):
- **Application Startup**: FastAPI lifespan context initializes DB, Redis, ML Runtime, LangChain providers, Hermes tools, provider registry
- **Gateway Layer**: POST /chat endpoint with JWT auth, rate limiting, idempotency check, envelope construction, internal client call to orchestrator
- **Orchestrator Intake**: Safety validation (ContentGuard), input redaction, intent classification (IntakeProcessor), workflow creation (PostgreSQL), plan generation (PlanEngine), execution dispatch (RuntimeKernel)
- **Agent Backend Selection**: BUTLER_AGENT_RUNTIME env var selects between LangGraphAgentBackendAdapter (langgraph) or HermesAgentBackend (legacy)
- **LangGraph Agent Execution**: ButlerChatModel wraps MLRuntime, ButlerToolFactory creates LangChain tools, tool binding with llm.bind_tools(), StateGraph execution with messages
- **Tool Execution**: ToolRegistry.get_spec(), ToolPolicy.evaluate() (risk tier, approval, sandbox), OperationRouter.route() (admission control, rate limiting, quota), SandboxManager.execute()
- **Middleware Chain**: RequestContextMiddleware (request_id, trace context), TenantContextMiddleware (tenant resolution from JWT), RuntimeContextMiddleware (runtime context creation)
- **Dependency Injection**: get_orchestrator_service() wires MemoryService, ToolsService, ButlerBlender, SmartRouter, agent backend, RuntimeKernel

**Integration Required**:
- Update Control Plane section to reflect actual orchestrator intake flow
- Update Model System section to reflect ML Runtime Manager and LangChain provider registry
- Update Tool System section to reflect ToolPolicy, OperationRouter, SandboxManager
- Update Context System section to reflect middleware chain (RequestContext, TenantContext, RuntimeContext)
- Update Agent Backend section to reflect LangGraph vs Hermes selection via BUTLER_AGENT_RUNTIME
- Add Dependency Injection section to reflect get_orchestrator_service() wiring pattern

---

# 1. System Layers (Canonical 7-Plane Architecture)

```text
[ User ]
   ↓ (encrypt with session key)

PLANE 1: EDGE
    Nano-Gatekeeper (Rust/Axum)
    → JWT decode, rate limit, complexity classify, cache check
    → Target: P95 < 30ms

PLANE 2: CONTROL
    ExecutionOrchestrator
    AutoModeEngine
    CostRouter
    PromptHub
    → Target: P95 < 50ms combined

PLANE 3: CONTEXT
    ContextSelector
    ContextBudgetManager
    ContextCompactor
    UnifiedRetrieval (parallel fan-out)
    → Target: P95 < 200ms

PLANE 4: INTELLIGENCE
    DeliberationEngine (Chain/ReAct/Tree/Graph)
    CouncilEngine (multi-model)
    ReflexionEngine (async, post-task)
    → Target: P95 < 1200ms (complexity 1-3)

PLANE 5: CREW
    DomainCrew (Map/Scout/Run/Gate/Sync)
    AgentBriefcase
    TaskLedger
    → Target: P95 < 5000ms (complexity 4-5)

PLANE 6: KNOWLEDGE
    MemoryService (multi-tier, encrypted)
    KnowledgeGraph (KGoT)
    ToolScope + ToolGraph
    → Throughput: 5K ops/sec on Redis warm tier

PLANE 7: INFRASTRUCTURE
    ModelPool (multi-provider)
    EncryptionService (E2E)
    ReliabilityLayer (CB + Retry + Fallback)
    ObservabilityStack (metrics + trace + log)

[ Cross-Cutting: Encryption Layer ]
    Tier A: User data (E2E encrypted)
    Tier B: System data (server encrypted)
    Tier C: Operational (plaintext)
    → ContextService: decryption boundary
    → MemoryService: encrypted storage
```

---

# 2. Encryption Layer (E2E Data Privacy)

**Core Principle**: Encrypt at rest → decrypt at execution boundary → wipe immediately

Full E2E encryption AND LLM reasoning on the same data is impossible (LLMs need plaintext). The design uses tiered encryption with controlled decryption at specific boundaries.

## 2.1 Encryption Tiers

### Tier A — MUST be E2E Encrypted

**User-private data that never leaves the client encrypted:**

- User messages (raw prompts)
- Conversation history
- Episodic memory (user-specific)
- Personal preferences
- Uploaded documents
- Tool results containing user data

**Storage**: Encrypted with user's session key, never stored plaintext on server.

### Tier B — Server-Encrypted (Not E2E)

**System-derived data encrypted at server level:**

- Knowledge graph (derived/shared)
- Aggregated embeddings
- Tool metadata
- System logs (sanitized)

**Storage**: Encrypted with server key (Fernet/KMS), accessible to server for operations.

### Tier C — Plaintext (Safe)

**Operational data that is safe to store plaintext:**

- Execution metadata
- Routing decisions
- Cost metrics
- System telemetry

**Storage**: Plaintext, no sensitive user data.

**Rule**:
```text
User-private → E2E
System-derived → server encrypted
Operational → plaintext (safe)
```

## 2.2 Key Management

### Hybrid Model

**1. User Master Key (UMK)**
- Generated on client (device/browser)
- NEVER leaves client
- Used to encrypt session keys
- Stored in client secure storage (Keychain, secure enclave)

**2. Session Key (SK)**
- Generated per session
- Used for encrypting actual data
- Encrypted with UMK
- Sent to server as encrypted(SK)
- Server cannot decrypt SK without UMK (which never leaves client)

**3. Server Key (Optional)**
- For server-side encryption fallback
- Stored in KMS/HSM
- Used for Tier B encryption (system-derived data)

### Storage

```text
Client:
    UMK (never leaves client)

Server:
    encrypted(SK)  (wrapped with UMK)
    encrypted(data) (encrypted with SK)
```

### Flow

```text
Client:
    1. Generate SK
    2. Encrypt SK with UMK → encrypted(SK)
    3. Encrypt data with SK → encrypted(data)
    4. Send encrypted(SK) + encrypted(data) to server

Server:
    1. Store encrypted(SK)
    2. Store encrypted(data)
    3. When needed: Request client to decrypt (or use secure enclave)
```

## 2.3 LLM Compatibility

### Decryption at Controlled Execution Boundary

**NOT doing:**
- Homomorphic encryption (too slow)
- Full encrypted inference (not practical)

**Correct design:**
```text
Encrypted Data
    ↓
Secure Decryption Zone (short-lived)
    ↓
LLM Processing (plaintext)
    ↓
Immediate wipe
```

### Where Decryption Happens

Decryption occurs at:
- **ContextService**: When selecting context for LLM
- **Deliberation Engine**: At input boundary before reasoning

### Critical Rule

```text
Decrypted data NEVER:
- stored
- logged
- cached
- reused across tenants
```

### Lifetime

Decrypted plaintext exists only for the duration of the execution window (< 1 second typically).

## 2.4 Encryption Service

### Domain Contract

```python
# domain/encryption/encryption_service_contract.py
from pydantic import BaseModel
from datetime import datetime

class EncryptedPayload(BaseModel):
    encrypted_data: str
    encrypted_session_key: str  # Wrapped with UMK
    tenant_id: str
    encryption_version: str
    created_at: datetime

class DecryptionRequest(BaseModel):
    encrypted_payload: EncryptedPayload
    tenant_id: str
    purpose: str  # "context_selection", "deliberation"

class EncryptionServiceContract:
    async def encrypt_payload(
        self,
        data: str,
        tenant_id: str,
        session_key: str,
    ) -> EncryptedPayload:
        """Encrypt payload with session key."""
        pass

    async def decrypt_payload(
        self,
        payload: EncryptedPayload,
        tenant_id: str,
    ) -> str:
        """Decrypt payload (requires client key unwrap)."""
        pass

    async def rotate_keys(
        self,
        tenant_id: str,
    ) -> None:
        """Rotate encryption keys for tenant."""
        pass

    async def encrypt_for_storage(
        self,
        data: str,
        tenant_id: str,
        tier: str,  # "A" (E2E) or "B" (server)
    ) -> EncryptedPayload:
        """Encrypt data for storage based on tier."""
        pass
```

## 2.5 Critical Rules (Non-Negotiable)

### 1. No Decrypted Persistence

```python
# NEVER do this
if decrypted:
    await memory_service.store(decrypted_data)  # ❌ FORBIDDEN

# ALWAYS do this
if decrypted:
    await encryption_service.encrypt(decrypted_data)
    await memory_service.store(encrypted_data)  # ✅ CORRECT
```

### 2. No Decrypted Logging

```python
# NEVER do this
logger.info(f"User message: {decrypted_message}")  # ❌ FORBIDDEN

# ALWAYS do this
logger.info(f"User message: [encrypted:{len(encrypted_data)}]")  # ✅ CORRECT
```

### 3. No Cross-Tenant Key Usage

```python
# NEVER do this
tenant_key = get_shared_key()  # ❌ FORBIDDEN

# ALWAYS do this
tenant_key = get_tenant_key(tenant_id)  # ✅ CORRECT
```

### 4. Short-Lived Plaintext

```python
# Decrypted data must be wiped immediately
decrypted = await encryption_service.decrypt(payload)
try:
    result = await llm.process(decrypted)
finally:
    del decrypted  # ✅ Wipe immediately
    secure_wipe(decrypted)  # ✅ Secure wipe
```

### 5. Context-Only Decryption

```python
# Decrypt ONLY what is used
# ❌ WRONG: Decrypt entire history
all_history = await memory_service.recall_all(decrypt=True)

# ✅ CORRECT: Decrypt only selected context
selection = await context_selector.select_context(query, limit=5)
decrypted_items = [
    await encryption_service.decrypt(item.encrypted_data)
    for item in selection.items
]
```

---

# 3. Control Plane (Critical)

## 3.1 ExecutionOrchestrator

**Purpose**: Routes requests to appropriate execution lanes based on complexity, budget, and tenant configuration.

**Current Implementation** (from Butler Backend Execution Flow Map):
- **Orchestrator Service** (`services/orchestrator/service.py`) owns the intake → classify → build context → generate response flow
- **Intake Entry Point**: `intake()` method receives ButlerEnvelope, performs safety checks, intent classification, workflow creation, plan generation, and execution dispatch
- **Graph Bypass**: Bypasses LangGraph to avoid circular dependency, calls core `_intake_core()` directly
- **Safety Validation**: ContentGuard validates input for safety policy compliance
- **Input Redaction**: `_redact_input()` removes sensitive information before processing
- **Intent Classification**: IntakeProcessor classifies intent and determines execution mode
- **Workflow Persistence**: Creates Workflow record in PostgreSQL with intent and context
- **Plan Generation**: PlanEngine creates execution plan with LLM
- **Execution Dispatch**: RuntimeKernel dispatches to selected execution strategy (HERMES_AGENT or DETERMINISTIC)
- **Output Safety Check**: ContentGuard validates output before returning
- **Memory Writeback**: Stores execution results in memory via `store.append_turn()`

**Responsibilities**:
- Receive ButlerRuntimeEnvelope
- Consult Auto Mode Engine for execution path decision
- Consult Cost Router for budget validation
- Dispatch to appropriate lane (LLM, ReAct, Domain Crew, Async Crew, Council)
- Enforce tenant budget limits
- Track execution metrics

**Domain Contract**:
```python
# domain/runtime/execution_orchestrator_contract.py
from enum import Enum
from pydantic import BaseModel
from typing import Optional, Dict, Any

class ExecutionLane(str, Enum):
    DETERMINISTIC_TOOL = "deterministic_tool"
    LLM_ANSWER = "llm_answer"
    LLM_WITH_TOOLS = "llm_with_tools"
    DOMAIN_CREW = "domain_crew"
    CREW_ASYNC = "crew_async"
    COUNCIL_MODE = "council_mode"

class ExecutionDecision(BaseModel):
    lane: ExecutionLane
    reasoning_mode: str  # chain, react, tree, graph
    confidence: float
    estimated_cost: float
    estimated_duration_ms: int

class ExecutionOrchestratorContract:
    async def decide_execution(
        self,
        envelope: ButlerRuntimeEnvelope,
        tenant_context: TenantContext,
    ) -> ExecutionDecision:
        """Decide execution lane based on complexity, budget, and tenant config."""
        pass

    async def dispatch(
        self,
        decision: ExecutionDecision,
        envelope: ButlerRuntimeEnvelope,
        tenant_context: TenantContext,
    ) -> ExecutionResult:
        """Dispatch to appropriate execution lane."""
        pass
```

## 3.2 Auto Mode Engine

**Purpose**: Default execution controller that decides execution path and escalates based on confidence.

**Responsibilities**:
- Analyze request complexity
- Select appropriate reasoning mode
- Decide when to escalate to higher-cost lanes
- Minimize cost while maintaining quality
- Early exit on sufficient confidence

**Domain Contract**:
```python
# domain/runtime/auto_mode_engine_contract.py
class AutoModeDecision(BaseModel):
    execution_lane: ExecutionLane
    reasoning_mode: str
    complexity_score: float  # 1.0-5.0
    confidence: float  # 0.0-1.0
    should_escalate: bool
    escalation_reason: Optional[str]

class AutoModeEngineContract:
    async def analyze_request(
        self,
        envelope: ButlerRuntimeEnvelope,
        tenant_context: TenantContext,
    ) -> AutoModeDecision:
        """Analyze request and decide execution path."""
        pass

    async def should_escalate(
        self,
        current_result: ExecutionResult,
        confidence_threshold: float,
    ) -> bool:
        """Decide if escalation is needed based on confidence."""
        pass
```

## 3.3 Cost Router

**Purpose**: Budget-aware execution routing that enforces tenant budget limits.

**Responsibilities**:
- Validate tenant budget before execution
- Estimate cost for proposed execution path
- Downgrade execution if budget is low
- Track actual cost during execution
- Enforce hard budget limits

**Domain Contract**:
```python
# domain/runtime/cost_router_contract.py
class CostEstimate(BaseModel):
    estimated_tokens: int
    estimated_cost_usd: float
    execution_lane: ExecutionLane
    reasoning_mode: str

class BudgetStatus(BaseModel):
    budget_remaining: float
    budget_total: float
    is_sufficient: bool
    recommended_downgrade: Optional[ExecutionLane]

class CostRouterContract:
    async def estimate_cost(
        self,
        decision: ExecutionDecision,
        tenant_context: TenantContext,
    ) -> CostEstimate:
        """Estimate cost for proposed execution path."""
        pass

    async def check_budget(
        self,
        estimate: CostEstimate,
        tenant_context: TenantContext,
    ) -> BudgetStatus:
        """Check if tenant has sufficient budget."""
        pass

    async def recommend_downgrade(
        self,
        current_lane: ExecutionLane,
        budget_status: BudgetStatus,
    ) -> Optional[ExecutionLane]:
        """Recommend lower-cost execution lane if budget is low."""
        pass
```

## 3.4 PromptHub

**Purpose**: Dynamic prompt system with versioning, tenant-aware overrides, and safety validation.

**Responsibilities**:
- Store and version prompt templates
- Resolve prompts with tenant overrides
- Validate prompt safety before execution
- Track prompt performance (rejection rate)
- Enable prompt learning loop

**Schema**:
```python
# domain/prompts/prompt_hub_contract.py
from datetime import datetime
from typing import Dict, Optional, List

class PromptTemplate(BaseModel):
    id: str
    name: str
    version: str
    content: str
    variables: Dict[str, str]
    domain: str
    agent_role: str
    tenant_id: Optional[str]  # None = global
    created_at: datetime
    is_active: bool

class PromptResolution(BaseModel):
    template: PromptTemplate
    variables: Dict[str, str]
    resolved_content: str
    source: str  # "tenant_override" or "global"

class PromptHubContract:
    async def resolve_prompt(
        self,
        name: str,
        tenant_id: str,
        variables: Dict[str, str],
    ) -> PromptResolution:
        """Resolve prompt with tenant override or global fallback."""
        pass

    async def validate_prompt(
        self,
        prompt: str,
        tenant_id: str,
    ) -> bool:
        """Validate prompt safety (no tool leakage, unsafe instructions)."""
        pass

    async def flag_prompt(
        self,
        template_id: str,
        reason: str,
    ) -> None:
        """Flag prompt for review if rejection rate is high."""
        pass

    async def get_prompt_layers(
        self,
        domain: str,
        agent_role: str,
        tenant_id: str,
    ) -> List[PromptTemplate]:
        """Get all prompt layers (base + domain + role + tenant)."""
        pass
```

**Prompt Layers**:
```
Base Prompt (system behavior)
+ Domain Prompt (finance/health/etc)
+ Agent Role Prompt (Map/Run/Gate)
+ Tenant Override
+ Runtime Injection (tools/memory/context)
```

---

# 4. Context System (SEPARATE SERVICE)

**CRITICAL**: ContextService is separate from MemoryService. Agents NEVER receive raw logs.

**Current Implementation** (from Butler Backend Execution Flow Map):
- **Middleware Chain** (`core/middleware.py`) - RequestContextMiddleware, TenantContextMiddleware, RuntimeContextMiddleware
- **RequestContextMiddleware** - Extracts/generates request_id, extracts OTel trace context
- **TenantContextMiddleware** - Gets JWT payload from state, tenant_resolver.resolve(), sets tenant_context_var
- **RuntimeContextMiddleware** - Gets tenant_context from state, RuntimeContext.create(), sets runtime_context_var
- **RuntimeContext** - Builds RuntimeContext with tenant_id, account_id, session_id, permissions

**Encryption Integration**: ContextService is a decryption boundary. It decrypts only selected context items for LLM processing, with immediate plaintext wipe after use.

## 4.1 Context Selector

**Purpose**: Relevance-based retrieval from memory, knowledge graph, and session state.

**Responsibilities**:
- Retrieve relevant episodic memories
- Retrieve relevant knowledge graph nodes
- Retrieve current task state
- Rank by relevance
- Enforce context budget limits

**Domain Contract**:
```python
# domain/context/context_selector_contract.py
from typing import List, Dict, Any

class ContextSource(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    GRAPH = "graph"
    SESSION = "session"

class ContextItem(BaseModel):
    content: str
    source: ContextSource
    relevance_score: float
    token_count: int
    metadata: Dict[str, Any]

class ContextSelection(BaseModel):
    items: List[ContextItem]
    total_tokens: int
    sources_used: List[ContextSource]

class ContextSelectorContract:
    async def select_context(
        self,
        query: str,
        tenant_id: str,
        domain: str,
        limit: int = 5,
    ) -> ContextSelection:
        """Retrieve relevant context from all sources."""
        pass
```

## 4.2 Context Budget Manager

**Purpose**: Enforce token limits on context to prevent bloat.

**Responsibilities**:
- Enforce MAX_CONTEXT = 4000 tokens (configurable)
- Track token count per context item
- Prioritize high-relevance items
- Signal when budget exceeded

**Domain Contract**:
```python
# domain/context/context_budget_manager_contract.py
class ContextBudget(BaseModel):
    max_tokens: int
    current_tokens: int
    remaining_tokens: int
    is_over_budget: bool

class ContextBudgetManagerContract:
    async def check_budget(
        self,
        selection: ContextSelection,
        max_tokens: int,
    ) -> ContextBudget:
        """Check if context exceeds token budget."""
        pass

    async def prioritize_items(
        self,
        selection: ContextSelection,
        budget: ContextBudget,
    ) -> ContextSelection:
        """Prioritize items to fit within budget."""
        pass
```

## 4.3 Context Compactor

**Purpose**: Compress context when budget exceeded while preserving critical information.

**Responsibilities**:
- Compress context when token limit exceeded
- Keep facts, decisions, evidence
- Remove repetition
- Preserve decision logic

**Domain Contract**:
```python
# domain/context/context_compactor_contract.py
class CompressionRule(BaseModel):
    keep_facts: bool = True
    remove_repetition: bool = True
    preserve_decisions: bool = True
    preserve_evidence: bool = True

class ContextCompactorContract:
    async def compress(
        self,
        selection: ContextSelection,
        rules: CompressionRule,
    ) -> ContextSelection:
        """Compress context to fit within budget."""
        pass
```

## 4.4 Unified Retrieval

**Purpose**: Single retrieval interface that queries memory, knowledge graph, and session state.

**Responsibilities**:
- Unified search across all context sources
- Deduplicate results
- Rank by relevance
- Return structured context

**Domain Contract**:
```python
# domain/context/unified_retrieval_contract.py
class UnifiedQuery(BaseModel):
    query: str
    tenant_id: str
    domain: str
    sources: List[ContextSource]
    limit: int = 5

class UnifiedRetrievalContract:
    async def retrieve(
        self,
        query: UnifiedQuery,
    ) -> ContextSelection:
        """Retrieve context from unified sources."""
        pass
```

**Context Composition**:
```
Context =
    Top Memory (episodic)
  + Relevant Knowledge (KGoT)
  + Current Task State
  + Tool Results (compressed)
```

---

# 5. Tool System (ToolScope + ToolGraph)

**Current Implementation** (from Butler Backend Execution Flow Map):
- **ToolRegistry** (`services/tools/executor.py`) - Fetches ToolSpec from canonical registry
- **ToolPolicy** (`services/tools/executor.py`) - Checks RiskTier, approval_required, sandbox_required
- **OperationRouter** (`services/tools/executor.py`) - Admission control, rate limiting, quota enforcement
- **SandboxManager** (`services/tools/executor.py`) - Executes tool in isolated sandbox if spec.sandbox_required
- **ButlerToolFactory** (`langchain/agent.py`) - Converts ButlerToolSpec to LangChain BaseTool with governance
- **Hermes Tool Loading** (`main.py`) - Loads Hermes tool implementations into Butler registry during startup

## 5.1 ToolScope Pipeline

**Purpose**: Full 6-layer pipeline for semantic tool retrieval and execution.

**Pipeline Layers**:
1. **Intent Layer**: Extract tool intent from query
2. **Semantic Layer**: Retrieve tools by embedding similarity
3. **Policy Layer**: Filter by tenant permissions and policies
4. **Rerank Layer**: Re-rank by relevance, cost, success rate
5. **Cutoff Layer**: Apply dynamic cutoff threshold
6. **Guardrail Layer**: Validate tool parameters before execution
7. **Feedback Layer**: Update tool metrics after execution

**Domain Contract**:
```python
# domain/tools/toolscope_contract.py
class ToolScopeResult(BaseModel):
    tools: List[ToolDefinition]
    intent: str
    filtered_count: int
    reranked: bool
    cutoff_applied: bool

class ToolScopeContract:
    async def retrieve_tools(
        self,
        query: str,
        tenant_id: str,
        domain: str,
    ) -> ToolScopeResult:
        """Execute full ToolScope pipeline."""
        pass
```

## 5.2 ToolGraph

**Purpose**: Multi-step tool chaining with dependency awareness.

**Responsibilities**:
- Build tool dependency graph
- Validate tool chains before execution
- Execute chains in correct order
- Track tool chain success/failure

**Domain Contract**:
```python
# domain/tools/tool_graph_contract.py
class ToolChain(BaseModel):
    tools: List[ToolDefinition]
    execution_order: List[str]  # tool_ids
    dependencies: Dict[str, List[str]]  # tool_id -> depends_on
    estimated_cost: float

class ToolGraphContract:
    async def build_chain(
        self,
        tools: List[ToolDefinition],
        goal: str,
    ) -> ToolChain:
        """Build optimal tool chain for goal."""
        pass

    async def validate_chain(
        self,
        chain: ToolChain,
    ) -> bool:
        """Validate tool chain dependencies."""
        pass

    async def execute_chain(
        self,
        chain: ToolChain,
        context: Dict[str, Any],
    ) -> ToolChainResult:
        """Execute tool chain in order."""
        pass
```

## 4.3 Tool Guardrails

**Purpose**: Validate tool parameters and execution before actual tool call.

**Domain Contract**:
```python
# domain/tools/tool_guardrails_contract.py
class ToolValidationResult(BaseModel):
    is_valid: bool
    reason: Optional[str]
    sanitized_params: Optional[Dict[str, Any]]

class ToolGuardrailsContract:
    async def validate_tool_call(
        self,
        tool: ToolDefinition,
        params: Dict[str, Any],
        tenant_id: str,
    ) -> ToolValidationResult:
        """Validate tool parameters and permissions."""
        pass
```

## 4.4 Tool Feedback Loop

**Purpose**: Update tool metrics based on execution results.

**Domain Contract**:
```python
# domain/tools/tool_feedback_contract.py
class ToolMetrics(BaseModel):
    tool_id: str
    success_count: int
    failure_count: int
    avg_latency_ms: float
    last_used: datetime

class ToolFeedbackContract:
    async def record_success(
        self,
        tool_id: str,
        latency_ms: float,
    ) -> None:
        """Record successful tool execution."""
        pass

    async def record_failure(
        self,
        tool_id: str,
        reason: str,
    ) -> None:
        """Record failed tool execution."""
        pass

    async def get_metrics(
        self,
        tool_id: str,
    ) -> ToolMetrics:
        """Get tool metrics for ranking."""
        pass
```

---

# 6. Deliberation Engine (Core Intelligence)

## 5.1 Reasoning Modes

**Supported Modes**:
- **Chain-of-Thought**: Linear reasoning (simple tasks)
- **ReAct**: Think → Act → Observe → Reflect (tool usage)
- **Tree-of-Thoughts**: Bounded branching (multiple paths)
- **Graph-of-Thoughts**: State merging via hashing (overlapping problems)
- **Self-Consistency**: Final voting (confidence)
- **Reflexion**: Learning from failure (post-task)

**Domain Contract**:
```python
# domain/deliberation/deliberation_engine_contract.py
class ReasoningMode(str, Enum):
    CHAIN = "chain"
    REACT = "react"
    TREE = "tree"
    GRAPH = "graph"
    SELF_CONSISTENCY = "self_consistency"
    REFLEXION = "reflexion"

class DeliberationConfig(BaseModel):
    mode: ReasoningMode
    max_depth: int = 4
    max_width: int = 3
    max_cost: float
    confidence_threshold: float = 0.9
    early_exit: bool = True

class DeliberationResult(BaseModel):
    final_answer: str
    reasoning_trace: List[str]
    confidence: float
    cost: float
    steps_taken: int

class DeliberationEngineContract:
    async def deliberate(
        self,
        query: str,
        context: ContextSelection,
        tools: List[ToolDefinition],
        config: DeliberationConfig,
    ) -> DeliberationResult:
        """Execute deliberation with specified mode."""
        pass

    async def should_early_exit(
        self,
        current_confidence: float,
        threshold: float,
    ) -> bool:
        """Decide if early exit is warranted."""
        pass
```

## 5.2 ReAct Loop

**Purpose**: Think → Act → Observe → Reflect loop for tool-based reasoning.

**Domain Contract**:
```python
# domain/deliberation/react_contract.py
class ReActStep(BaseModel):
    step_number: int
    thought: str
    action: Optional[str]  # tool call
    observation: Optional[str]  # tool result
    reflection: Optional[str]

class ReActContract:
    async def execute_step(
        self,
        query: str,
        context: ContextSelection,
        tools: List[ToolDefinition],
        previous_steps: List[ReActStep],
    ) -> ReActStep:
        """Execute single ReAct step."""
        pass

    async def run_loop(
        self,
        query: str,
        context: ContextSelection,
        tools: List[ToolDefinition],
        max_steps: int = 10,
    ) -> DeliberationResult:
        """Run full ReAct loop."""
        pass
```

## 5.3 Graph Optimization

**Purpose**: Merge duplicate states in Graph-of-Thoughts via hashing.

**Domain Contract**:
```python
# domain/deliberation/graph_optimization_contract.py
class GraphState(BaseModel):
    state_hash: str
    content: str
    parent_hashes: List[str]

class GraphOptimizationContract:
    async def detect_duplicate_state(
        self,
        state: str,
        existing_states: List[GraphState],
    ) -> Optional[GraphState]:
        """Detect if state already exists via hash."""
        pass

    async def merge_states(
        self,
        state1: GraphState,
        state2: GraphState,
    ) -> GraphState:
        """Merge two similar states."""
        pass
```

## 5.4 Budget Control

**Purpose**: Enforce max depth, width, and cost limits.

**Domain Contract**:
```python
# domain/deliberation/budget_control_contract.py
class BudgetState(BaseModel):
    depth: int
    width: int
    cost: float
    max_depth: int
    max_width: int
    max_cost: float
    is_exceeded: bool

class BudgetControlContract:
    async def check_budget(
        self,
        current_state: BudgetState,
    ) -> BudgetState:
        """Check if deliberation budget exceeded."""
        pass

    async def enforce_limit(
        self,
        current_state: BudgetState,
    ) -> bool:
        """Enforce budget limit (return False if exceeded)."""
        pass
```

---

# 7. Council Engine (Dual-Mode Design)

## Overview — Two Modes, Two Purposes

```
NORMAL COUNCIL
    3 models → parallel reasoning → one debate round → consensus vote
    Use when: Important decision, needs cross-model validation
    Cost: ~3× single model call
    Latency: 15–25s
    Consensus method: Embedding similarity vote

DEEP COUNCIL
    3 large debaters + 3 sharp critics + 1 chair → structured parliamentary debate
    Use when: Critical/irreversible decision, complex multi-sided problem, high-stakes domain
    Cost: ~20–40× single model call
    Latency: 60–180s
    Consensus method: Resolution document with majority + minority dissent
```

Triggering conditions:
- **Normal Council**: User sets mode=COUNCIL, OR domain is in `council_domains` config, OR confidence < 0.6 after CREW_ASYNC
- **Deep Council**: User sets mode=DEEP_COUNCIL explicitly, OR decision is flagged as irreversible, OR Normal Council produces consensus_score < 0.65

## 7.1 Normal Council (Refined)

### Architecture

```
Round 1: INDEPENDENT REASONING (parallel, no cross-visibility)
    Model A (Primary)    → Position A + confidence + reasoning chain
    Model B (Challenger) → Position B + confidence + reasoning chain
    Model C (Domain)     → Position C + confidence + reasoning chain
         ↓
Round 2: DEBATE (each model sees peers' reasoning, NOT their answers)
    Model A sees: B_reasoning + C_reasoning → revised Position A
    Model B sees: A_reasoning + C_reasoning → revised Position B
    Model C sees: A_reasoning + B_reasoning → revised Position C
         ↓
CONSENSUS MEASUREMENT
    Embed all 3 final answers
    Pairwise cosine similarity
    Weighted by confidence
         ↓
    score ≥ 0.80 → return consensus answer
    score < 0.80 → Gate Agent tiebreaker
```

### Model Assignment

```python
NORMAL_COUNCIL_MEMBERS = [
    CouncilMember(
        role="primary",
        provider="anthropic",
        model="claude-sonnet-4-5",
        briefing="You are the primary analyst. Reason carefully and state your position.",
    ),
    CouncilMember(
        role="challenger",
        provider="openai",
        model="gpt-4o",
        briefing="You are the challenger. Look for flaws in conventional wisdom.",
    ),
    CouncilMember(
        role="domain_specialist",
        provider="anthropic",
        model="claude-haiku-3-5",
        briefing="You are the domain specialist. Focus on domain-specific constraints.",
    ),
]
```

### Consensus Measurement (Concrete)

```python
def measure_consensus(results: List[MemberResult]) -> ConsensusScore:
    
    embeddings = [embedder.embed(r.final_answer) for r in results]
    
    # Pairwise cosine similarity
    pairs = [
        (i, j, cosine_similarity(embeddings[i], embeddings[j]))
        for i in range(len(embeddings))
        for j in range(i+1, len(embeddings))
    ]
    
    # Weight by confidence product
    weighted_sim = sum(
        sim * results[i].confidence * results[j].confidence
        for i, j, sim in pairs
    ) / sum(
        results[i].confidence * results[j].confidence
        for i, j, _ in pairs
    )
    
    # Identify majority answer (highest confidence in agreement cluster)
    agreement_cluster = [
        results[i] for i, j, sim in pairs
        if sim >= 0.75  # Strong agreement threshold
        for r in [results[i], results[j]]
    ]
    
    majority = max(agreement_cluster or results, key=lambda r: r.confidence)
    
    return ConsensusScore(
        score=weighted_sim,
        majority_answer=majority.final_answer,
        majority_confidence=majority.confidence,
        dissenting_views=[r for r in results if r != majority],
    )
```

## 7.2 Deep Council (Parliamentary Architecture)

### The Full Cast

```
CHAIR (1 model — large, orchestrator only)
    Role: Frame the motion, enforce debate rules, synthesize resolution
    Model: claude-opus-4-5 (needs highest reasoning for synthesis)
    Speaks: Round 0 (framing) + Final Resolution only
    Does NOT: Argue a position, take sides

MAIN DEBATERS (3 models — large, opinionated)
    PROPOSER:   Argues for the primary/conventional approach
    OPPOSITION: Argues for an alternative or challenges the primary
    ANALYST:    Evidence-based synthesis, no strong position, identifies facts

    Models: claude-opus-4-5, gpt-4o, gemini-pro-1-5 (or equivalent tier)
    Each model assigned a fixed role for the entire debate

CRITICS (3 models — small, sharp, question-only)
    DEVIL'S ADVOCATE: Challenges whichever position appears strongest
    FACT CHECKER:     Demands evidence for every unsupported claim
    EDGE CASE FINDER: Identifies failure modes, extreme scenarios, blind spots

    Models: claude-haiku-3-5 (cheap but precise)
    Rule: Critics NEVER propose answers. They ONLY question and challenge.
    Each critic produces: max 3 questions per round (hard limit)
```

### The Seven-Round Debate Chain

```
ROUND 0:  Motion Framing       [Chair only]
ROUND 1:  Opening Statements   [Debaters, isolated]
ROUND 2:  Critical Interrogation [Critics challenge Round 1]
ROUND 3:  First Rebuttal       [Debaters respond to Round 2 critics]
ROUND 4:  Cross-Examination    [Debaters challenge each other]
ROUND 5:  Critical Re-Examination [Critics identify remaining gaps]
ROUND 6:  Position Amendment   [Debaters may revise their positions]
ROUND 7:  Closing Arguments    [Final position, no revision]
RESOLUTION: Chair synthesizes  [Structured document]
```

### Information Flow Per Round (CRITICAL)

```
ROUND 1 — Each debater sees:
    ✅ Formal motion (from Round 0)
    ✅ Their own role briefing
    ❌ Other debaters' positions
    ❌ Critics' questions

ROUND 2 — Each critic sees:
    ✅ Formal motion
    ✅ ALL three Round 1 opening statements
    ✅ Their critic role
    ❌ Other critics' questions

ROUND 3 — Each debater sees:
    ✅ Formal motion
    ✅ Their own Round 1 statement
    ✅ ALL other debaters' Round 1 statements
    ✅ ALL critics' Round 2 questions
    ❌ Other debaters' Round 3 responses

ROUND 4 — Each debater sees:
    ✅ Everything from Rounds 1-3
    ✅ Other debaters' Round 3 responses
    They submit: ONE targeted question to ONE other debater

ROUND 5 — Each critic sees:
    ✅ Everything from Rounds 1-4
    They submit: max 2 questions (focused on UNRESOLVED disagreements only)

ROUND 6 — Each debater sees:
    ✅ Everything from Rounds 1-5
    They submit: Updated position (MUST state what changed and WHY)

ROUND 7 — Each debater sees:
    ✅ Everything from Rounds 1-6
    They submit: Final closing argument (no further changes)

RESOLUTION — Chair sees:
    ✅ Complete transcript of all 7 rounds
    ✅ All positions, all challenges, all amendments
    Produces: Structured resolution document
```

### Mode Comparison Table

| Dimension | Normal Council | Deep Council (Full) | Deep Council (Abbrev.) |
|-----------|---------------|---------------------|----------------------|
| Rounds | 2 | 7 | 5 |
| Models total | 3 | 7 | 7 |
| Model tier | Mid (Sonnet/4o) | Large (Opus/4o/Gemini) + Small critics | Same |
| Critics | None | 3 sharp critics | 3 sharp critics |
| Cross-examination | None | Yes (sequential) | No |
| Amendment round | No | Yes | No |
| Resolution type | Consensus answer | Structured document | Structured document |
| Minority dissent recorded | No | Yes | Yes |
| Audit trail | Confidence score | Full transcript hash | Full transcript hash |
| Cost estimate | ~$0.10 | ~$2.00–5.00 | ~$1.20–3.00 |
| Latency estimate | 15–25s | 90–180s | 50–90s |
| Use case | Important decisions | Critical/irreversible | High-stakes, time-limited |

### When Each Mode Fires

```python
class CouncilModeSelector:
    
    async def select_mode(
        self,
        envelope: ButlerRuntimeEnvelope,
        escalation_reason: Optional[str],
    ) -> CouncilMode:
        
        # Explicit user request always wins
        if envelope.mode == UserMode.DEEP_COUNCIL:
            return CouncilMode.DEEP
        if envelope.mode == UserMode.COUNCIL:
            return CouncilMode.NORMAL
        
        # Automatic escalation to Deep Council
        deep_triggers = [
            envelope.domain in IRREVERSIBLE_DECISION_DOMAINS,
            escalation_reason == "normal_council_no_consensus",
            envelope.decision_metadata.get("is_irreversible", False),
            envelope.tenant_config.always_deep_council_for_domain(envelope.domain),
        ]
        
        if any(deep_triggers):
            return CouncilMode.DEEP
        
        return CouncilMode.NORMAL


IRREVERSIBLE_DECISION_DOMAINS = {
    "legal_action",
    "financial_large",
    "medical_treatment",
    "infrastructure_change",
    "strategic_pivot",
    "personnel_decision",
}
```

### Cost Guard (Non-Negotiable)

Deep Council is expensive. These limits are hard:

```python
class DeepCouncilCostGuard:
    
    async def pre_flight_check(
        self,
        config: DeepCouncilConfig,
        tenant_context: TenantContext,
    ) -> CostCheckResult:
        
        estimated_cost = self._estimate_deep_council_cost(config)
        
        if estimated_cost > tenant_context.budget_remaining:
            # Try abbreviated mode
            abbrev_cost = self._estimate_abbreviated_cost(config)
            if abbrev_cost <= tenant_context.budget_remaining:
                return CostCheckResult(
                    approved=True,
                    mode=DeepMode.ABBREVIATED,
                    estimated_cost=abbrev_cost,
                    reason="Full Deep Council over budget, using abbreviated mode",
                )
            else:
                # Fall back to Normal Council
                return CostCheckResult(
                    approved=True,
                    mode=DeepMode.FALLBACK_NORMAL,
                    estimated_cost=self._estimate_normal_cost(),
                    reason="Deep Council over budget, falling back to Normal Council",
                )
        
        return CostCheckResult(approved=True, mode=DeepMode.FULL, estimated_cost=estimated_cost)
```

---

# 8. Domain Crews (No Generic Agents)

**Current Implementation** (from Butler Backend Execution Flow Map):
- **Agent Backend Selection** (`services/orchestrator/backends.py`) - BUTLER_AGENT_RUNTIME env var determines LangGraph vs legacy Hermes
- **LangGraph Agent Backend** (`langchain/backend.py`) - LangGraphAgentBackendAdapter wraps LangGraphAgentBackend
- **Hermes Agent Backend** (`services/orchestrator/backends.py`) - Single-step local agent backend for legacy mode
- **RuntimeKernel** (`domain/orchestrator/runtime_kernel.py`) - Routes to HERMES_AGENT or DETERMINISTIC strategy
- **CrewAI Integration** (`butler_runtime/agent/`) - CrewAIBuilder with ContentGuard for security guardrails
- **ButlerChatModel** (`langchain/agent.py`) - LangChain model wrapper around MLRuntimeManager
- **ButlerToolFactory** (`langchain/agent.py`) - Converts ButlerToolSpec to LangChain BaseTool with governance
- **Tool Binding** (`langchain/agent.py`) - llm.bind_tools(tools) for function calling
- **StateGraph Execution** (`langchain/backend.py`) - LangGraph StateGraph execution with messages

## 8.1 Crew Structure

**Agent Roles**:
- **Map**: Planning only (decompose task into steps)
- **Scout**: Information gathering (retrieve context, knowledge)
- **Run**: Execution only (execute tools, perform actions)
- **Gate**: Validation only (validate output against constraints)
- **Sync**: Coordination only (orchestrate crew, manage loop budget)

**Domain Contract**:
```python
# domain/crews/domain_crew_contract.py
from enum import Enum

class AgentRole(str, Enum):
    MAP = "map"
    SCOUT = "scout"
    RUN = "run"
    GATE = "gate"
    SYNC = "sync"

class CrewContext(BaseModel):
    task_id: str
    domain: str
    briefcase: AgentBriefcase
    ledger: TaskLedger

class AgentOutput(BaseModel):
    agent_role: AgentRole
    output: str
    metadata: Dict[str, Any]

class DomainCrewContract:
    async def execute_agent(
        self,
        role: AgentRole,
        context: CrewContext,
        input_data: Dict[str, Any],
    ) -> AgentOutput:
        """Execute single agent."""
        pass

    async def run_crew(
        self,
        task: str,
        domain: str,
        briefcase: AgentBriefcase,
        config: DeliberationConfig,
    ) -> DeliberationResult:
        """Run full crew with Map → Scout → Run → Gate loop."""
        pass
```

## 8.2 Agent Briefcase

**Purpose**: Runtime injection of skills, preferences, and constraints.

**Schema**:
```python
# domain/memory/agent_briefcase.py
class AgentBriefcase(BaseModel):
    task_id: str
    allowed_tools: List[str]
    operating_skills: List[str]  # For Run agent
    strategic_preferences: List[str]  # For Map agent
    negative_constraints: List[str]  # For Gate agent
```

## 6.3 Task Ledger

**Purpose**: Internal scratchpad for Sync orchestrator.

**Schema**:
```python
# domain/memory/task_ledger.py
class LedgerAction(str, Enum):
    MAP_PLAN = "map_plan"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    GATE_REJECTION = "gate_rejection"
    GATE_APPROVAL = "gate_approval"

class TaskLedgerEntry(BaseModel):
    task_id: str
    step_number: int
    agent_role: AgentRole
    action: LedgerAction
    payload: Dict[str, Any]
    compute_cost: float
```

---

# 9. Knowledge System (KGoT)

## 9.1 Knowledge Graph Overview

**Purpose**: Store structured knowledge as claims, sources, entities, and metrics.

**Schema**:
```python
# domain/knowledge/knowledge_graph_contract.py
from enum import Enum

class NodeType(str, Enum):
    CLAIM = "claim"
    SOURCE = "source"
    ENTITY = "entity"
    METRIC = "metric"

class EdgeType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    RELATED_TO = "related_to"

class KnowledgeNode(BaseModel):
    node_id: str
    tenant_id: str
    node_type: NodeType
    content: str
    metadata: Dict[str, Any]

class KnowledgeEdge(BaseModel):
    edge_id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    confidence: float

class KnowledgeGraphContract:
    async def add_node(
        self,
        node: KnowledgeNode,
    ) -> str:
        """Add node to knowledge graph."""
        pass

    async def add_edge(
        self,
        edge: KnowledgeEdge,
    ) -> str:
        """Add edge to knowledge graph."""
        pass

    async def detect_contradictions(
        self,
        claim_id: str,
    ) -> List[KnowledgeEdge]:
        """Detect contradictions for a claim."""
        pass

    async def trace_evidence(
        self,
        claim_id: str,
    ) -> List[KnowledgeNode]:
        """Trace evidence chain for a claim."""
        pass
```

---

# 10. Memory System (Butler-Controlled)

**CRITICAL**: Only Butler writes memory. Agents are stateless.

**Encryption Integration**: MemoryService stores all Tier A (E2E) and Tier B (server-encrypted) data encrypted. Decryption only happens at ContextService boundary.

## 10.1 Memory Types

- **Episodic Memory**: Lessons learned from tasks (AgentMemoryNode)
- **Semantic Memory**: Embeddings for similarity search
- **Structured Graph Memory**: Knowledge graph for structured truth

## 10.2 MemoryService Contract

```python
# domain/memory/memory_service_contract.py
from enum import Enum

class MemoryTier(str, Enum):
    WARM = "warm"  # Redis (fast access)
    COLD = "cold"  # PostgreSQL (persistent)
    VECTOR = "vector"  # Qdrant (similarity)
    EPISODIC = "episodic"  # PostgreSQL (lessons)
    GRAPH = "graph"  # Neo4j (structured)

class MemoryNode(BaseModel):
    node_id: str
    tenant_id: str
    domain: str
    memory_type: MemoryType
    content: str
    weight: float = 1.0
    created_at: datetime
    last_accessed: datetime

class MemoryServiceContract:
    async def store(
        self,
        node: MemoryNode,
        tier: MemoryTier,
    ) -> str:
        """Store memory node in specified tier."""
        pass

    async def recall(
        self,
        query: str,
        tenant_id: str,
        domain: str,
        tier: MemoryTier,
        limit: int = 5,
    ) -> List[MemoryNode]:
        """Recall memory nodes from specified tier."""
        pass

    async def build_context(
        self,
        query: str,
        tenant_id: str,
        domain: str,
    ) -> ContextSelection:
        """Build context from all tiers."""
        pass
```

---

# 11. Multi-Tenant Architecture

## 11.1 Hard Isolation Rules

**Tenant NEVER shares**:
- Memory
- Knowledge graph
- Prompt overrides
- Tool permissions
- Model keys

**CRITICAL**: NO cross-tenant embedding similarity (vector leakage = data breach)

## 11.2 Tenant Context Envelope

**Schema**:
```python
# domain/tenant/tenant_context.py
class TenantContext(BaseModel):
    tenant_id: str
    plan: str  # "free", "pro", "enterprise"
    budget_remaining: float
    budget_total: float
    model_pool_id: str
    permissions: Dict[str, Any]
    prompt_overrides: Dict[str, str]  # prompt_name -> content
```

## 11.3 Data Partitioning Strategy

| Layer | Strategy |
|-------|----------|
| Redis | tenant_id prefix |
| PostgreSQL | row-level security (tenant_id column) |
| Vector DB | namespace per tenant |
| Knowledge Graph | tenant-scoped subgraph |
| PromptHub | global + tenant override |

---

# 12. Reliability Layer (MANDATORY)

## 12.1 Circuit Breaker

**Purpose**: Disable component when failure rate exceeds threshold.

**Domain Contract**:
```python
# domain/reliability/circuit_breaker_contract.py
from enum import Enum

class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit tripped
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreakerContract:
    async def check_state(
        self,
        component_id: str,
    ) -> CircuitState:
        """Check circuit breaker state."""
        pass

    async def record_failure(
        self,
        component_id: str,
    ) -> None:
        """Record component failure."""
        pass

    async def record_success(
        self,
        component_id: str,
    ) -> None:
        """Record component success."""
        pass

    async def trip_circuit(
        self,
        component_id: str,
    ) -> None:
        """Trip circuit (disable component)."""
        pass
```

## 12.2 Retry Policy

**Purpose**: Retry with exponential backoff.

**Domain Contract**:
```python
# domain/reliability/retry_policy_contract.py
class RetryConfig(BaseModel):
    max_retries: int = 2
    backoff_base_ms: int = 100
    max_backoff_ms: int = 5000

class RetryPolicyContract:
    async def should_retry(
        self,
        attempt: int,
        error: Exception,
        config: RetryConfig,
    ) -> bool:
        """Decide if retry is warranted."""
        pass

    async def get_backoff_ms(
        self,
        attempt: int,
        config: RetryConfig,
    ) -> int:
        """Calculate backoff delay."""
        pass
```

## 12.3 Timeout Controls

**Purpose**: Enforce maximum time per step.

**Domain Contract**:
```python
# domain/reliability/timeout_control_contract.py
class TimeoutConfig(BaseModel):
    max_time_per_step_ms: int = 5000
    max_total_time_ms: int = 30000

class TimeoutControlContract:
    async def check_timeout(
        self,
        start_time: datetime,
        config: TimeoutConfig,
    ) -> bool:
        """Check if timeout exceeded."""
        pass
```

## 12.4 Fallback Strategy

**Purpose**: Progressive fallback when primary execution fails.

**Fallback Chain**:
```
Crew → ReAct → LLM → Static
```

**Domain Contract**:
```python
# domain/reliability/fallback_strategy_contract.py
class FallbackDecision(BaseModel):
    should_fallback: bool
    fallback_lane: ExecutionLane
    reason: str

class FallbackStrategyContract:
    async def should_fallback(
        self,
        current_lane: ExecutionLane,
        error: Exception,
        tenant_context: TenantContext,
    ) -> FallbackDecision:
        """Decide if fallback is warranted."""
        pass

    async def execute_fallback(
        self,
        decision: FallbackDecision,
        envelope: ButlerRuntimeEnvelope,
        tenant_context: TenantContext,
    ) -> ExecutionResult:
        """Execute fallback lane."""
        pass
```

---

# 13. Model System

**Current Implementation** (from Butler Backend Execution Flow Map):
- **ML Runtime Manager** (`core/deps.py`) - Singleton MLRuntimeManager creation in DI registry
- **ML Runtime Startup** - Warms up ML runtime with provider connections during application lifespan
- **LangChain Provider Registry** - Initializes all LangChain provider adapters during startup
- **Provider Registry** - Initializes all provider connections during application startup
- **ButlerChatModel** - LangChain model wrapper around MLRuntimeManager
- **ChatModelFactory** - Creates ButlerChatModel with runtime_manager, tenant_id, tool_context

**Dependency Injection** (from Butler Backend Execution Flow Map):
- **DependencyRegistry** (`core/deps.py`) - Singleton registry for all services
- **get_orchestrator_service()** - Request-scoped factory that assembles fully-wired OrchestratorService
- **get_memory_service()** - Request-scoped MemoryService with 4-tier architecture
- **get_tools_service()** - Request-scoped ToolExecutor with compiled specs
- **get_blender()** - ButlerBlender with memory + tools
- **create_agent_backend()** - Factory creates LangGraph or Hermes backend with all dependencies
- **RuntimeKernel assembly** - deterministic_backend + hermes_backend (agent)

## 13.1 Model Pool

**Purpose**: Multi-provider rotation, quota-aware failover, compute arbitrage.

**Schema**:
```python
# domain/models/model_pool_contract.py
from enum import Enum

class PoolStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    QUOTA_FIRST = "quota_first"
    ARBITRAGE_FIRST = "arbitrage_first"
    CUSTOM = "custom"

class SubscriptionPool(BaseModel):
    pool_id: str
    tenant_id: str
    base_provider: str
    members: List[str]
    strategy: PoolStrategy
    enabled: bool

class ModelPoolContract:
    async def select_provider(
        self,
        pool_id: str,
        model: str,
    ) -> str:
        """Select provider based on strategy."""
        pass

    async def record_rate_limit(
        self,
        provider: str,
    ) -> None:
        """Record rate limit hit for failover."""
        pass

    async def switch_provider(
        self,
        pool_id: str,
        current_provider: str,
    ) -> str:
        """Switch to next available provider."""
        pass
```

## 13.2 Cost-Aware Routing

**Purpose**: Select cheapest capable model for task.

**Domain Contract**:
```python
# domain/models/cost_routing_contract.py
class ModelOption(BaseModel):
    provider: str
    model: str
    cost_per_1k_tokens: float
    capabilities: List[str]

class CostRoutingContract:
    async def select_model(
        self,
        task_complexity: float,
        required_capabilities: List[str],
        budget: float,
    ) -> ModelOption:
        """Select cheapest capable model."""
        pass
```

---

# 13. User Mode System

## 12.1 Modes

| Mode | Behavior |
|------|----------|
| Auto | Default - Auto Mode Engine decides path |
| Quick | Fast, cheap (LLM_ANSWER) |
| Smart | ReAct with tools |
| Expert | Domain Crew with Tree/Graph |
| Deep | Async Crew with deep research |
| Council | Multi-model consensus |

## 12.2 Auto Mode

**Purpose**: Default execution controller that decides path and escalates based on confidence.

**Responsibilities**:
- Decide execution path
- Escalate based on confidence
- Minimize cost
- Early exit on sufficient confidence

**Domain Contract**:
```python
# domain/runtime/auto_mode_contract.py
class UserMode(str, Enum):
    AUTO = "auto"
    QUICK = "quick"
    SMART = "smart"
    EXPERT = "expert"
    DEEP = "deep"
    COUNCIL = "council"

class AutoModeContract:
    async def execute_auto(
        self,
        envelope: ButlerRuntimeEnvelope,
        tenant_context: TenantContext,
    ) -> ExecutionResult:
        """Execute with Auto Mode (decides path)."""
        pass
```

---

# 14. Execution Flow (Step-by-Step)

## 13.1 Request Flow

```text
1. User Request → ButlerRuntimeEnvelope
2. Nano-Gatekeeper → Routing Decision (complexity, domain, execution_class)
3. ExecutionOrchestrator → Auto Mode Engine Analysis
4. Cost Router → Budget Validation
5. ContextService → Context Selection (memory + knowledge + session)
6. PromptHub → Prompt Resolution (base + domain + role + tenant)
7. Execution Dispatch:
   - Complexity 1/2: LLM_ANSWER
   - Complexity 3: LLM_WITH_TOOLS (ReAct)
   - Complexity 4: DOMAIN_CREW (Tree/Graph)
   - Complexity 5: CREW_ASYNC (deep research)
8. ToolScope → Tool Retrieval (Intent → Semantic → Policy → Rerank → Cutoff)
9. ToolGraph → Tool Chain Execution
10. Deliberation Engine → Reasoning (Chain/ReAct/Tree/Graph/Self-Consistency)
11. Domain Crew → Agent Execution (Map → Scout → Run → Gate loop)
12. Gate Agent → Output Validation
13. Reflexion Loop → Post-Task Learning (if enabled)
14. MemoryService → Lesson Storage
15. Response → ButlerRuntimeEnvelope
```

## 13.2 Control Flow (Auto Mode + Escalation)

```text
Auto Mode Engine:
1. Analyze request complexity (1-5)
2. Select initial execution lane based on complexity
3. Execute with selected lane
4. Measure confidence
5. If confidence < threshold AND budget allows:
   - Escalate to higher-cost lane
   - Repeat from step 3
6. Else:
   - Return result

Escalation Chain:
LLM_ANSWER → LLM_WITH_TOOLS → DOMAIN_CREW → CREW_ASYNC → COUNCIL_MODE
```

---

# 15. Data Flow Between Layers

## 14.1 Request → Response

```text
[User Request]
    ↓
[Nano-Gatekeeper]
    → NanoRoutingDecision (complexity, domain, execution_class)
    ↓
[ExecutionOrchestrator]
    → Receives envelope + routing decision
    → Calls Auto Mode Engine
    ↓
[Auto Mode Engine]
    → AutoModeDecision (lane, reasoning_mode, confidence)
    ↓
[Cost Router]
    → CostEstimate (tokens, cost)
    → BudgetStatus (sufficient?, recommended_downgrade)
    ↓
[ContextService]
    → ContextSelection (items from episodic, semantic, graph, session)
    ↓
[PromptHub]
    → PromptResolution (template, variables, resolved_content)
    ↓
[Execution Dispatch]
    → Based on lane:
      - LLM_ANSWER: Direct MLRuntime call
      - LLM_WITH_TOOLS: DeliberationEngine (ReAct)
      - DOMAIN_CREW: DomainCrew + DeliberationEngine (Tree/Graph)
      - CREW_ASYNC: Async queue + DomainCrew
      - COUNCIL_MODE: CouncilEngine
    ↓
[ToolScope]
    → ToolScopeResult (filtered, reranked tools)
    ↓
[ToolGraph]
    → ToolChain (execution order, dependencies)
    ↓
[DeliberationEngine]
    → DeliberationResult (final_answer, reasoning_trace, confidence)
    ↓
[Domain Crew]
    → AgentOutput (per agent)
    → TaskLedger (step-by-step tracking)
    ↓
[Gate Agent]
    → Validation (pass/reject)
    ↓
[Reflexion Loop] (async, post-task)
    → AgentMemoryNode (new lessons)
    ↓
[MemoryService]
    → Store lessons in EPISODIC tier
    ↓
[Response]
    → ButlerRuntimeEnvelope with result
```

---

# 16. Multi-Tenant Isolation Strategy

## 15.1 Tenant Context Propagation

```text
Every request includes:
- tenant_id (from JWT)
- TenantContext (envelope with budget, permissions, overrides)

TenantContext is propagated through:
- ExecutionOrchestrator
- Cost Router
- ContextService
- PromptHub
- MemoryService
- ToolScope
- Model Pool

All data access is scoped to tenant_id:
- Redis: key prefix = f"{tenant_id}:"
- PostgreSQL: WHERE tenant_id = ?
- Vector DB: namespace = tenant_id
- Knowledge Graph: subgraph = tenant_id
- PromptHub: tenant_override > global
```

## 15.2 Isolation Enforcement

**Database Level**:
- Row-level security on PostgreSQL (tenant_id column)
- Namespace isolation on Vector DB
- Subgraph isolation on Knowledge Graph

**Application Level**:
- TenantContext validation on all service calls
- Prompt override resolution (tenant > global)
- Tool permission filtering per tenant
- Model pool isolation per tenant

**Infrastructure Level**:
- Redis key prefixing
- Separate queues per tenant (optional for high-volume tenants)

---

# 17. Context and Memory Flow

## 16.1 Context Building Flow

```text
[Query]
    ↓
[ContextSelector]
    → UnifiedQuery (query, tenant_id, domain, sources, limit)
    ↓
[UnifiedRetrieval]
    → Parallel retrieval from:
      - EPISODIC: Lessons from past tasks
      - SEMANTIC: Embeddings similarity
      - GRAPH: Knowledge graph nodes
      - SESSION: Current conversation state
    ↓
[ContextBudgetManager]
    → Check total tokens against MAX_CONTEXT (4000)
    → If over budget: prioritize by relevance
    ↓
[ContextCompactor] (if over budget)
    → Compress while preserving:
      - Facts
      - Decisions
      - Evidence
    → Remove repetition
    ↓
[ContextSelection]
    → Final context items
    → Total token count
    ↓
[DeliberationEngine / DomainCrew]
    → Inject context into agent prompts
```

## 16.2 Memory Writing Flow

```text
[Task Completion]
    ↓
[Reflexion Engine] (async, isolated)
    → Parse TaskLedger
    → Parse user corrections/feedback
    → Generate AgentMemoryNode entries:
      - Type: PREFERENCE (user preferences)
      - Type: LESSON (learned patterns)
    ↓
[MemoryService]
    → Store in EPISODIC tier (PostgreSQL)
    → Update GRAPH tier (Neo4j)
    → Update SEMANTIC tier (embeddings)
    ↓
[Next Task]
    → ContextSelector retrieves from EPISODIC
    → Compiled into AgentBriefcase
```

---

# 18. Tool Execution Pipeline

## 17.1 ToolScope Pipeline

```text
[Query]
    ↓
[Intent Layer]
    → Extract tool intent
    → Map to tool categories
    ↓
[Semantic Layer]
    → Embed query
    → Retrieve tools by similarity
    → Top-K retrieval
    ↓
[Policy Layer]
    → Filter by tenant permissions
    → Filter by domain policies
    → Filter by tool availability
    ↓
[Rerank Layer]
    → Re-rank by:
      - Relevance
      - Cost
      - Success rate
      - Recent usage
    ↓
[Cutoff Layer]
    → Apply dynamic cutoff threshold
    → Return top N tools
    ↓
[Guardrail Layer]
    → Validate tool parameters
    → Sanitize inputs
    ↓
[Execution]
    → Execute tool call
    ↓
[Feedback Layer]
    → Update tool metrics
    → Record success/failure
    → Update success rate
```

## 17.2 ToolGraph Execution

```text
[Goal]
    ↓
[ToolGraph.build_chain]
    → Analyze goal dependencies
    → Build tool dependency graph
    → Determine execution order
    → Validate chain
    ↓
[ToolGraph.execute_chain]
    → Execute tools in order
    → Pass outputs to dependent tools
    → Track chain state
    ↓
[ToolChainResult]
    → Final result
    → Intermediate outputs
    → Execution trace
```

---

# 19. Reasoning Engine Design

## 18.1 Mode Selection

```text
[Task Complexity]
    ↓
[Auto Mode Engine]
    → Complexity 1-2: CHAIN (linear reasoning)
    → Complexity 3: REACT (tool usage)
    → Complexity 4: TREE (multiple paths)
    → Complexity 5: GRAPH (overlapping problems)
    ↓
[DeliberationEngine]
    → Execute selected mode
    → Enforce budget (depth, width, cost)
    → Early exit on confidence threshold
```

## 18.2 ReAct Integration

```text
[Query]
    ↓
[ReAct.run_loop]
    → For each step:
      1. THINK: Analyze current state
      2. DECIDE: Choose action (tool or answer)
      3. ACT: Execute tool (via ToolScope)
      4. OBSERVE: Get tool result
      5. REFLECT: Update understanding
    → Stop when:
      - Confidence > threshold
      - Max steps reached
      - Budget exceeded
    ↓
[DeliberationResult]
    → Final answer
    → Reasoning trace
    → Confidence
```

## 18.3 Tree-of-Thoughts Integration

```text
[Query]
    ↓
[Tree Deliberation]
    → Generate multiple reasoning paths
    → For each path:
      - Execute reasoning step
      - Evaluate confidence
      - Branch if confidence < threshold
    → Enforce max_width (parallel paths)
    → Enforce max_depth (path length)
    → Merge results from all paths
    ↓
[Self-Consistency Voting]
    → Vote on final answer from all paths
    → Return majority vote
```

## 18.4 Graph-of-Thoughts Integration

```text
[Query]
    ↓
[Graph Deliberation]
    → Generate reasoning states
    → For each state:
      - Compute state hash
      - Check if duplicate exists
      - If duplicate: merge states
      - If new: add to graph
    → Build state graph
    → Traverse graph to find optimal path
    ↓
[DeliberationResult]
    → Final answer
    → State graph trace
```

---

# 20. Reliability and Failure Handling

## 19.1 Failure Detection

```text
[Circuit Breaker]
    → Monitor failure rate per component
    → If failure_rate > threshold: trip circuit
    → If circuit OPEN: reject requests immediately
    → After cooldown: attempt HALF_OPEN (test recovery)

[Retry Policy]
    → On transient error: retry with backoff
    → Max retries: 2
    → Backoff: exponential (100ms → 200ms → 400ms)
    → Max backoff: 5000ms

[Timeout Control]
    → Track start time per step
    → If step_time > max_time_per_step: timeout
    → If total_time > max_total_time: abort
```

## 19.2 Fallback Execution

```text
[Primary Execution Fails]
    ↓
[FallbackStrategy.should_fallback]
    → Analyze error type
    → Check tenant budget
    → Decide fallback lane
    ↓
[Fallback Chain]
    → Crew fails → Try ReAct
    → ReAct fails → Try LLM
    → LLM fails → Try Static response
    ↓
[FallbackStrategy.execute_fallback]
    → Execute fallback lane
    → Return result with fallback_reason
```

## 19.3 Observability

**Metrics to Track**:
- Latency (P50, P95, P99)
- Cost per request
- Hallucination rate
- Tool success rate
- Drift rate
- Prompt performance (rejection rate)
- Circuit breaker state
- Retry count
- Timeout count
- Fallback count
- Answer confidence vs user satisfaction

**Tracing**:
- Distributed tracing across all layers
- Trace ID propagated through entire request
- Span for each component execution

**Logging**:
- Structured logs with tenant_id, request_id
- Log levels: DEBUG, INFO, WARN, ERROR
- Sensitive data redaction

---

# 21. Configuration (No Hardcoding)

## 20.1 Environment Variables

```bash
# System
MAX_CONTEXT_TOKENS=4000
MAX_DEPTH=4
MAX_WIDTH=3
CONFIDENCE_THRESHOLD=0.9

# Multi-tenant
DEFAULT_TENANT_ID=default
TENANT_ISOLATION_ENABLED=true

# Context
CONTEXT_COMPRESSION_ENABLED=true
CONTEXT_COMPRESSION_KEEP_FACTS=true
CONTEXT_COMPRESSION_REMOVE_REPETITION=true

# ToolScope
TOOLSCOPE_ENABLED=true
TOOLSCOPE_DEFAULT_LIMIT=5
TOOLSCOPE_CUTOFF_THRESHOLD=0.7

# Deliberation
DELIBERATION_MODE=react
DELIBERATION_EARLY_EXIT=true

# Reliability
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_TIMEOUT_SECONDS=60
RETRY_MAX_ATTEMPTS=2
TIMEOUT_MAX_PER_STEP_MS=5000
TIMEOUT_MAX_TOTAL_MS=30000

# Model Pool
MODEL_POOL_STRATEGY=quota_first
MODEL_POOL_FAILOVER_ENABLED=true

# Auto Mode
AUTO_MODE_ENABLED=true
AUTO_MODE_ESCALATION_ENABLED=true

# Encryption (E2E)
ENCRYPTION_ENABLED=true
ENCRYPTION_ALGORITHM=AES_256_GCM
ENCRYPTION_KEY_ROTATION_DAYS=90
ENCRYPTION_SESSION_KEY_TTL_HOURS=24
ENCRYPTION_PLAINTEXT_TTL_SECONDS=1
```

## 20.2 Tenant Configuration

```python
# Stored in database (tenant_config table)
class TenantConfig(BaseModel):
    tenant_id: str
    plan: str
    budget_total: float
    model_pool_id: str
    permissions: Dict[str, bool]
    prompt_overrides: Dict[str, str]
    tool_permissions: List[str]
    max_context_tokens: int  # Override default
    max_depth: int  # Override default
    max_width: int  # Override default
    confidence_threshold: float  # Override default
```

## 20.3 Prompt Configuration

```python
# Stored in database (prompt_templates table)
# Global prompts (tenant_id = NULL)
# Tenant overrides (tenant_id = specific tenant)
```

---

# 22. Security (Strict)

## 21.1 Guardrails

**Input Guard**:
- ContentGuard validation
- PII detection
- Prompt injection detection

**Tool Guard**:
- Tool parameter validation
- Permission checking
- Risk assessment

**Output Guard**:
- ContentGuard validation
- PII redaction
- Safety check

## 22.2 Rules

- No direct tool execution without validation
- No unsafe domain responses
- No memory injection attacks
- No cross-tenant data leakage
- No unbounded loops
- **No decrypted data persistence (E2E encryption)**
- **No decrypted logging (E2E encryption)**
- **No cross-tenant key usage (E2E encryption)**
- **Short-lived plaintext only (E2E encryption)**
- **Context-only decryption (E2E encryption)**

---

# 23. Implementation Phases

## Phase 1: Nano-Gatekeeper (6-8 days)
- Rust Gateway (Axum) setup
- JWT decryption and tenant extraction
- Rate limiting per tenant
- gRPC client to Python vLLM worker
- Python vLLM worker with Gemma 4 Edge
- Structured generation (outlines/instructor)
- NanoRoutingDecision schema
- MemoryService HOT Redis integration
- Complexity 1 conversational wrapping
- gRPC drift classification endpoint
- Comprehensive tests
- Performance testing (sub-50ms latency)

## Phase 2: Encryption Service Foundation (3-4 days)
- EncryptionService domain contract
- AES-256-GCM encryption/decryption implementation
- Session key generation and management
- EncryptedPayload schema
- Key rotation mechanism
- Unit tests for encryption/decryption
- Integration tests for key management
- Performance testing (encryption/decryption < 10ms)

## Phase 3: Client-Side Key Management (2-3 days)
- User Master Key (UMK) generation on client
- Session Key (SK) generation and wrapping
- Client secure storage integration
- Key exchange protocol
- Client SDK for encryption
- End-to-end tests for key management

## Phase 4: Control Plane (5-7 days)
- ExecutionOrchestrator implementation
- Auto Mode Engine implementation
- Cost Router implementation
- PromptHub implementation
- Tenant Context Envelope
- Budget enforcement
- Integration tests

## Phase 5: Context System (4-6 days)
- ContextService implementation
- Context Selector implementation
- Context Budget Manager implementation
- Context Compactor implementation
- Unified Retrieval implementation
- Separation from MemoryService
- Integration tests

## Phase 6: MemoryService Encryption Integration (2-3 days)
- MemoryService encryption for Tier A data (E2E)
- MemoryService encryption for Tier B data (server)
- Encrypted storage schema
- Decryption at retrieval boundary
- Integration tests for encryption flows

## Phase 7: ContextService Decryption Integration (2-3 days)
- ContextService decryption at selection boundary
- Decryption only for selected context items
- Plaintext lifetime enforcement
- Integration with EncryptionService
- Integration tests for decryption flows

## Phase 8: Tool System (5-7 days)
- ToolScope full pipeline implementation
- ToolGraph implementation
- Tool Guardrails implementation
- Tool Feedback Loop implementation
- Integration with Deliberation Engine
- Integration tests

## Phase 9: Deliberation Engine (6-8 days)
- Chain-of-Thought implementation
- ReAct loop implementation
- Tree-of-Thoughts implementation
- Graph-of-Thoughts implementation
- Self-Consistency voting implementation
- Budget control implementation
- Graph optimization implementation
- Integration tests

## Phase 10: Domain Crews (5-7 days)
- Agent Briefcase implementation
- Task Ledger implementation
- Map agent implementation
- Scout agent implementation
- Run agent implementation
- Gate agent implementation
- Sync agent implementation
- Domain Crew orchestration
- Integration tests

## Phase 11: Knowledge System (3-5 days)
- Knowledge Graph implementation
- KGoT node/edge types
- Contradiction detection
- Evidence tracing
- Integration with ContextService
- Integration tests

## Phase 12: Multi-Tenant Architecture (NON-NEGOTIABLE) (4-6 days)
- Tenant Context Envelope implementation
- Data partitioning (Redis, PostgreSQL, Vector DB, Graph)
- Prompt override resolution
- Model pool per tenant
- Budget enforcement per tenant
- Cross-tenant leakage prevention
- Integration tests

## Phase 13: Model System (3-5 days)
- Model Pool Manager implementation
- Cost-aware routing implementation
- Multi-provider failover
- Quota tracking
- Integration tests

## Phase 14: Reliability Layer (4-6 days)
- Circuit Breaker implementation
- Retry Policy implementation
- Timeout Control implementation
- Fallback Strategy implementation
- Observability (metrics, tracing, logging)
- Integration tests

## Phase 15: User Mode System (3-5 days)
- User Mode implementation (Auto, Quick, Smart, Expert, Deep, Council)
- Auto Mode integration with ExecutionOrchestrator
- Mode escalation logic
- Integration tests

## Phase 16: End-to-End Integration (5-7 days)
- Full request flow testing
- All layers integration
- Multi-tenant testing
- Load testing (1M ops, 10K RPS)
- Performance testing (P95 < 1.5s)
- Cost testing (<$0.01 per request)

## Phase 17: Security Hardening (3-5 days)
- Input/Output Guardrails
- PII detection/redaction
- Prompt injection detection
- Memory injection attack prevention
- Cross-tenant leakage prevention tests
- Encryption audit (E2E)
- Security penetration testing

## Phase 18: Documentation and Handoff (3-5 days)
- Architecture documentation
- API documentation
- Runbooks
- Deployment guides
- Monitoring guides
- Troubleshooting guides

---

# 24. Success Criteria

- **Cost**: <$0.01 per average request (70-80% in cheap lanes)
- **Latency**: P95 < 1.5s for complexity 1-3, < 10s for complexity 4-5
- **Nano-Gatekeeper Latency**: P95 < 50ms for routing decisions
- **Scalability**: 1M+ ops/day, 10K RPS
- **Accuracy**: > 90% confidence threshold hit rate
- **Nano-Gatekeeper Accuracy**: > 95% routing accuracy vs heavy model
- **Nano-Gatekeeper Cache**: > 30% cache hit rate for common queries
- **Safety**: 0 L3/L4 auto-executions without approval
- **Reliability**: 99.9% uptime with graceful degradation
- **Model Pool**: < 1% failover rate, < 100ms failover latency
- **Council Mode**: > 80% consensus score on critical tasks
- **Intent Drift**: < 5% hard stop rate, < 15% warning rate
- **Tool Graph**: < 5% invalid tool call rate
- **Auto-Research**: > 70% success rate, < 3 iterations average
- **Unified Retrieval**: 50% latency reduction vs separate retrievals
- **Encryption (E2E)**: 100% of Tier A data encrypted at rest
- **Encryption (E2E)**: 0 decrypted data persistence violations
- **Encryption (E2E)**: 0 decrypted logging violations
- **Encryption (E2E)**: < 10ms encryption/decryption latency
- **Encryption (E2E)**: 100% key rotation compliance
- **Encryption (E2E)**: 0 cross-tenant key usage violations

---

# 25. Next Steps

After plan confirmation:
1. Implement Phase 1 (Nano-Gatekeeper Architecture)
2. Implement Phase 2 (Encryption Service Foundation)
3. Implement Phase 3 (Client-Side Key Management)
4. Implement Phase 4 (Control Plane)
5. Implement Phase 5 (Context System)
6. Implement Phase 6 (MemoryService Encryption Integration)
7. Implement Phase 7 (ContextService Decryption Integration)
8. Implement Phase 8 (Tool System)
9. Implement Phase 9 (Deliberation Engine)
10. Implement Phase 10 (Domain Crews)
11. Implement Phase 11 (Knowledge System)
12. Implement Phase 12 (Multi-Tenant Architecture)
13. Implement Phase 13 (Model System)
14. Implement Phase 14 (Reliability Layer)
15. Implement Phase 15 (User Mode System)
16. Implement Phase 16 (End-to-End Integration)
17. Implement Phase 17 (Security Hardening)
18. Implement Phase 18 (Documentation and Handoff)
