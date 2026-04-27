# BIS v2 — Personal Intelligence Operating System
## Complete Technical Architecture: Birth to Death, 0 → 100%

---

# PART 0 — WHAT THIS SYSTEM IS

BIS v2 is not a chatbot. It is a personal intelligence operating system that manages every dimension of a human life from birth records to end-of-life planning. It knows your finances, your health, your relationships, your career, your projects, your memories, and your mental state. It reasons across all of them without ever mixing raw data between domains.

The system is built on one law: every domain owns its data absolutely, communicates only through approved bridges, and the human is always the final authority.

It covers:

Finance — every rupee, every debt, every investment, every goal from your first pocket money to your retirement drawdown.

Health — every diagnosis, every medication, every lab result, every mood score, every therapy session, every fitness entry from birth records to end-of-life care.

Projects — every task, every milestone, every decision, every codebase, every research paper, every learning goal, completely isolated from personal data.

Social Graph — every person who matters to you, your history with them, their important dates, your relationship health, your family structure.

History Graph — the long-term memory of your entire life, every significant event across every domain, chains showing how one life event caused another, memories about yourself and memories about others clearly attributed.

Digital Twin — a live computed model of who you are right now, built from summaries of all domains, powering every AI agent that works for you.

Study, Research, Work, Code, Ideate, Brainstorm, Learn — all handled through the Project and Knowledge domains with specialized agents for every intellectual activity.

---

# PART 1 — THE ABSOLUTE DOMAIN LAW

Before any code is written, every engineer reads this once and recites it back.

DOMAIN WALLS ARE ABSOLUTE. No domain reads another domain's raw data under any circumstance. The Digital Twin reads summaries only, never raw records. Project Management reads nothing from any personal domain, ever. The History Graph is write-only from domains and read-only by the user. Mental health data has a separate encryption layer that cannot be broken even if the primary session key is compromised.

The only approved data flows are:

Finance sends financial milestone events to History Graph. Finance sends a computed summary to Digital Twin.

Health sends health event markers to History Graph. Health sends a status-only summary to Digital Twin. Mental health within Health has its own sub-encryption and never sends raw data anywhere.

Projects send professional completion events to History Graph. Projects send task summary to Digital Twin. Projects receive team member names from Social Graph only, nothing else.

Social Graph sends relationship event markers to History Graph. Social Graph sends contact summary to Digital Twin. Social Graph sends team member names to Projects.

History Graph sends major life event markers to Digital Twin. History Graph never sends clinical detail, financial amounts, or relationship specifics.

Any code that violates these flows raises a CrossDomainViolation exception. There are no exceptions to this rule. There are no emergency bypasses. There is no admin override.

---

# PART 2 — SYSTEM ARCHITECTURE OVERVIEW

The system runs across seven planes.

PLANE 1 is the Edge. A Rust gateway built with Axum handles every incoming request. It does JWT decoding, rate limiting per tenant, complexity classification, and cache checking. Target latency is under 30 milliseconds at P95. Nothing expensive happens here.

PLANE 2 is Control. The Python execution orchestrator decides which lane a request goes to. The Auto Mode Engine escalates only when necessary. The Cost Router enforces budget. The Prompt Hub resolves layered prompt templates. Target is under 50 milliseconds combined.

PLANE 3 is Context. The Context Selector retrieves relevant memories, knowledge graph nodes, and session state in parallel. The Budget Manager enforces a hard limit of 4000 tokens. The Compactor compresses when over budget. The Decryption Boundary is the only place in the system where encrypted user data becomes plaintext. Target is under 200 milliseconds.

PLANE 4 is Intelligence. The Deliberation Engine runs Chain of Thought, ReAct loops, Tree of Thoughts, and Graph of Thoughts depending on complexity. The Council Engine runs multi-model debates for critical decisions. The Reflexion Engine runs asynchronously after task completion to write verified lessons to memory.

PLANE 5 is Crew. Domain crews of five agents handle complex multi-step tasks. Map plans the task. Scout gathers information. Run executes tools. Gate validates output. Sync orchestrates the loop and enforces budget. Target is under 5 seconds at P95 for complexity 4 and 5 tasks.

PLANE 6 is Knowledge. The Memory Service operates across four tiers: Redis for warm recent context, PostgreSQL for persistent episodic memory, Qdrant for semantic vector search, and Neo4j for structured knowledge relationships. The Knowledge Graph stores claims, sources, entities, and metrics with contradiction detection.

PLANE 7 is Infrastructure. The Model Pool manages multiple AI providers with quota-aware failover. The Encryption Service handles end-to-end encryption. The Reliability Layer provides circuit breakers, retry policies, and fallback chains. The Observability Stack tracks every metric, trace, and log.

---

# PART 3 — DIGITAL TWIN

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

# PART 4 — PERSONAL FINANCE DOMAIN

The Finance Domain owns every financial record of your life from your first bank account to your final estate.

What it covers: all bank accounts checking savings credit investment loan and mortgage, all income streams salary freelance passive rental, all expenses with automatic categorization and subcategory, budgets by category and period with rollover support, financial goals emergency fund vacation house down payment retirement debt payoff custom, investment portfolio across stocks bonds ETFs and crypto, debt management with payoff plans and interest tracking, net worth calculation at every point in time with historical trend, tax-related categorization, subscription tracking showing every recurring charge, bill management with due dates.

What it deliberately does not cover: health-related spending is tracked as an expense category but never analyzed as health data. Professional income is tracked but career trajectory lives in History Graph. Family member finances live in their own twin and require explicit consent to view jointly.

The core data structures are:

Account holds institution name, account type, user-assigned nickname, currency, current balance encrypted at rest, credit limit if applicable, interest rate, whether it is the primary account, when it was linked, and when it was last synced.

Transaction holds the account, amount where negative means expense and positive means income, raw bank description encrypted, a BIS-cleaned merchant name, automatic category and subcategory, merchant name and location, date, whether it is recurring with a link to the recurring item, user tags and notes, and whether it is excluded from analysis.

Transaction categories span: salary, freelance income, investment income, rental income, other income on the income side, then rent and mortgage, utilities, home maintenance for housing, then groceries, dining, transport, health expenses, clothing for daily living, then savings transfers, investments, debt payments for financial movements, then entertainment, travel, subscriptions, education for lifestyle.

Budget holds a category, period monthly or weekly or annual, the budget limit, whether unused budget rolls over, the current amount spent as a computed field, the remaining amount as a computed field, an alert threshold defaulting to 80 percent, and the period start and end dates.

Financial Goal holds title, goal type, target amount, current amount, monthly contribution, target date, the linked account that holds this money, priority rank, and computed fields for progress percentage, estimated months remaining, and whether it is on track.

Net Worth Snapshot is computed daily and never modified after creation. It holds total assets, total liabilities, net worth, and a breakdown by asset and liability type. This creates a permanent historical record of your financial trajectory.

The finance intelligence agents are:

FinanceScout pulls transactions from connected accounts through open banking APIs, runs ML classification for categories accepting user corrections as training signal, detects recurring patterns, and flags anomalies like unusual merchants or unusual amounts.

FinancePlanner runs budget versus actual analysis, calculates goal progress, forecasts cash flow for the next 30, 90, and 180 days, models debt payoff scenarios, and runs what-if analysis such as what happens to my goals if I cut dining spending by 30 percent.

FinanceAlert sends low balance warnings, budget overrun alerts at the configured threshold, bill due reminders 3 days and 1 day in advance, unusual transaction flags for review, goal milestone celebrations, and periodic subscription audits showing the full list of active recurring charges.

The only events Finance sends to History Graph are: goal achieved, debt paid off, major purchase like a house or car, significant income change, user-tagged financial crisis event, and net worth milestones at 10K 100K 500K 1M and so on. No transaction amounts, no balance details, only event type plus a category like milestone and the date.

Finance across your whole life means: your first salary, your first investment, your debt accumulation and payoff journey, your home purchase, your children's education fund, your retirement savings progress, and eventually your drawdown phase. All of it tracked, analyzed, and advised on by agents that know your full financial history.

---

# PART 5 — HEALTH BANK

The Health Bank is the most private domain in the system. Every piece of data is Tier A encrypted meaning end-to-end with a key that never leaves your device. Mental health data within Health Bank has an additional sub-encryption layer derived from your master key plus a mental health salt. Even if your primary session key is compromised, your mental health records remain protected.

Health data is never used to train any model. Health data is never shared with any other domain except the two approved bridges: event markers to History Graph with no clinical detail, and a single status word to Digital Twin.

What Health Bank covers: medical conditions with ICD codes and status, all medications current and historical with dosage and refill tracking, all appointments upcoming and historical with pre and post notes, all lab results blood work imaging and other diagnostics, vital signs blood pressure heart rate weight temperature blood glucose and more as time series data, mental health including mood tracking therapy notes assessments and journals, fitness including daily activity sleep nutrition and hydration, genetic information and family health history, insurance coverage claims and deductibles, a daily symptoms log, allergies and contraindications, and vaccination records.

What Health Bank deliberately does not cover: health-related financial transactions live in Finance. Health impact on work performance goes to History Graph only through event markers. Mental health impact on relationships goes to History Graph only.

The core data structures are:

Medical Condition holds the condition name, ICD-10 code where known, status as active resolved managed or monitoring, diagnosis date, resolution date, diagnosing provider, encrypted notes, linked medications, and linked documents.

Medication holds name, generic name, dosage, route of administration oral topical injection inhaled, frequency, prescribing provider, what condition it was prescribed for, start date, end date, whether it is active, refill date, refills remaining, user-reported side effects, and encrypted instructions.

Health Appointment holds provider name and type, specialty, appointment type as checkup followup procedure therapy or emergency, scheduled time, location, whether it is telehealth, status as upcoming completed missed or cancelled, encrypted pre-appointment notes for what to discuss, encrypted post-appointment notes for what was discussed, and any documents generated like referrals or summaries.

Vital Sign Entry is a time series record. Each entry holds measurement time, source as manual device or provider, device identifier if applicable, and all the possible vital measurements: systolic and diastolic blood pressure, heart rate, weight in kilograms, height in centimeters, BMI computed from weight and height, temperature in celsius, blood oxygen percentage, blood glucose, and HbA1c. Only the measurements actually taken are recorded.

Mental Health Entry is the most sensitive record in the entire system. It requires the additional mental health sub-key to decrypt. It holds the entry type as mood log therapy note formal assessment journal or crisis flag. Mood logs capture mood score energy level anxiety level and sleep quality each on a 1 to 10 scale. Therapy entries capture therapist name session number and therapy type CBT DBT Psychodynamic EMDR. Assessment entries capture the assessment type PHQ-9 or GAD-7 or others, the score, and the clinical interpretation. All free text content is encrypted with the mental health sub-key. A crisis flag immediately generates an urgent attention flag in the Digital Twin and triggers resource display. Mental health entries are never in AI context unless you explicitly invoke mental health reflection mode.

Fitness Entry is a daily log. It holds date, source as manual or Apple Health or Garmin or Fitbit or Google Fit, step count, active minutes, individual workout records, sleep start and end time, total sleep hours, sleep quality, deep sleep hours, REM sleep hours, calories consumed, macronutrients protein carbs fat, water intake, and body composition from smart scale if available.

The health intelligence agents are:

HealthScout pulls from connected health devices and apps, runs OCR on uploaded lab reports and medical documents to extract structured data, monitors medication refill deadlines and generates reminders, and flags gaps in vitals logging.

HealthAnalyst runs trend analysis such as blood pressure trending upward over three months, detects correlations such as poor sleep preceding low mood preceding poor diet the next day, tracks medication adherence, interprets lab results with appropriate not-medical-advice disclaimers, and tracks progress toward fitness goals.

HealthCoordinator manages appointment scheduling reminders, tracks whether referred specialist appointments were actually booked, tracks insurance claim status, sends prescription refill reminders two weeks and three days in advance, and generates pre-appointment preparation summaries of what to discuss and what documents to bring.

MentalHealthGuardian is a completely separate agent with no access to any other domain. It analyzes mood trends over time, detects potential crisis indicators from sudden score drops or specific language patterns, detects therapy session gaps, maintains a consistently gentle non-clinical tone, links to appropriate resources when needed, and never shares any mental health data with any other system component.

Health across your whole life means: your birth records and childhood vaccinations, your first diagnoses, your medication history across decades, your fitness evolution, your mental health journey including therapy and growth, your chronic condition management, your aging and the health events that shape it, and eventually your end-of-life care documentation. All of it private, all of it yours.

---

# PART 6 — PROJECT MANAGEMENT DOMAIN

Project Management has zero connection to personal domains. This is an architectural constraint, not a configuration setting. Project agents receive no TwinContext, no HealthContext, no FinanceContext. They can reference Social Graph for team member names and contacts only. They can write professional events to History Graph only.

The reason is simple: work data and personal data should never mix. Your health status should not leak into your project context. Your financial situation should not influence how your project agent advises you. Team members referenced in a project get no access to your personal life domains whatsoever.

What Project Management covers: all projects personal work side-projects learning and open-source, all tasks with full structure including subtasks dependencies and checklists, milestones with completion tracking, decision records capturing context rationale and eventual outcome, meeting and idea notes, team member references with roles only, time tracking estimated versus actual, velocity tracking, deadline risk analysis, and project briefings for daily standups weekly reviews and pre-meeting context.

The core data structures are:

Project holds title, description, status as planning active on-hold completed archived or cancelled, priority as critical high medium or low, project type as personal work side-project learning or open-source, timeline with start date and target date, team members list with roles only, tags, parent project for sub-projects, linked related projects, and computed metrics for task count completion count overdue count and completion percentage.

Task holds title, description, status as todo in-progress blocked in-review done or cancelled, priority, assignment to a Social Graph person by name only with no personal data, creator, timeline with due date estimated hours and actual hours, parent task for subtasks, subtask list, task dependencies, tags, checklist items, attachments, and blocker information if blocked.

Milestone holds title, description, due date, completion status, completion timestamp, and the list of linked tasks.

Project Decision is a critical record. It captures context meaning what situation prompted this decision, the decision itself, alternatives that were considered, the rationale, who made it, when it was made, and later what the outcome was. This creates a permanent institutional memory for every significant decision in your professional life.

Project Note captures meeting notes, ideas, research findings, blocker descriptions, and feedback with links to the relevant project and optionally the relevant task.

Team Member is a lightweight reference: an optional link to a Social Graph person, a display name for this project, their role such as designer or dev lead or client, whether they are external, and a contact hint like email them rather than the actual email address.

The project intelligence agents are:

ProjectPlanner decomposes project goals into complete task trees, estimates timelines based on task complexity and your historical velocity, identifies dependencies that might create bottlenecks, suggests milestones, and proactively identifies structural gaps such as a project missing a testing phase or a launch plan.

ProjectMonitor tracks task completion rates against plan, identifies tasks that have been blocked for too long, detects deadline risk by counting tasks due in the next period versus tasks completed per day at current velocity, and tracks velocity trends over the project's life.

ProjectBriefing generates your daily standup summary of what is due today and what is blocked, your weekly review of what was accomplished and what slipped, pre-meeting context when you have a call with someone about a project with full status, risk alerts when a project milestone is at risk, and post-project retrospectives capturing what worked and what did not.

Projects across your whole life means: your school assignments, your university research projects, your first work projects, your side businesses, your open source contributions, your creative projects, your lifelong learning projects for every new skill or field, your entrepreneurial ventures, and your personal projects from home renovation to writing a book. All tracked, all connected to your professional history, none leaking into your personal health or financial records.

---

# PART 7 — STUDY AND LEARNING AS PROJECTS

Study and learning are a category of project in the Project domain. They get their own project type of learning and their own specialized agent behaviors.

A learning project has all the structure of a regular project plus a curriculum structure where the milestones are learning modules or chapters, the tasks are study sessions and exercises and assessments, and the decision records capture conceptual breakthroughs and things that clicked versus things that needed revisiting.

The ProjectPlanner in learning mode decomposes a learning goal into a curriculum, estimates time based on the complexity of the subject and your historical learning velocity, identifies prerequisite dependencies between topics, and creates spaced repetition reminders as tasks.

For research projects the same structure applies with additional task types for literature review, hypothesis formation, experiment design, data collection, analysis, and write-up. Decision records become research decisions capturing why a methodology was chosen and what the outcome was.

For coding projects tasks map to features and bug fixes and refactors, milestones map to releases, and the codebase itself links as an attachment to the project. The ProjectBriefing in coding mode generates commit-level context summaries before work sessions.

All intellectual work from learning a new programming language to researching a medical condition to building a product to writing a thesis runs through this domain. The History Graph captures the professional milestones: course completed, skill acquired, project shipped, degree earned, research published.

---

# PART 8 — SOCIAL GRAPH DOMAIN

The Social Graph is not a contact list. It is a relationship model that understands who people are to you, your history with them, what you know about them, how different groups in your life relate to each other, and who should be considered when making a given decision.

What it covers: every person in your life with their relationship type to you, your relationship history with each person, what you remember about them including preferences birthdays and important dates, group memberships and group dynamics, interaction logging with sentiment, silence detection when you have not contacted someone you care about, and upcoming important date tracking across your entire network.

The consent model is critical. Everything in the Social Graph is your memory of other people, not their data. You remember John's birthday because you noted it, not because John entered it into your system. This means the data belongs to you, is stored in your twin, is never shared with the person it concerns without explicit consent, and is never used to construct a profile of that person for any external purpose.

Relationship types span: self, partner, child, parent, sibling, grandparent, grandchild, extended family on the family side, then close friend, friend, acquaintance on the friendship side, then colleague, manager, direct report, mentor, mentee, client, vendor on the professional side, then doctor, therapist, and caregiver for care relationships.

Privacy tiers determine what the system can surface in different contexts: intimate tier for partner and children allows high data sharing in relevant contexts, close tier for close friends and parents allows moderate sharing, social tier for friends and colleagues allows limited sharing, professional tier for work contacts shows work data only, minimal tier for acquaintances shows name and context only.

Person record holds full name, preferred name, nickname, pronouns, relationship type, relationship group such as immediate family or work team or college friends, closeness level from 1 to 5, privacy tier, encrypted contact information phone email address and social handles, known information about them including birthday birthplace occupation interests and preferences, important dates with their types, how you met them, an encrypted shared history summary you wrote, last interaction date and your target interaction frequency, and the computed upcoming important dates within 30 days.

Relationship record captures how two people in your graph relate to each other, not just how they relate to you. This allows the system to understand that two colleagues are also married to each other, or that two friends who used to be close had a falling out. You note this context, and the system uses it to give better advice when those people are relevant to a decision.

Group record captures labeled collections of people: your immediate family, your college friend group, your work team, your community group. Each group has its own shared context description capturing what this group is about.

Interaction Log captures significant interactions, not every message. A dinner with a close friend is worth logging. An email thread about scheduling is not. Each log entry captures the interaction type, date, duration, location, an encrypted summary of what was discussed, your sentiment tag of good neutral or difficult, and whether there is a follow-up needed.

The social intelligence agents are:

RelationshipScout monitors upcoming important dates for your entire network with appropriate lead time so you have time to prepare, detects silences when you have not contacted someone you care about beyond your target frequency, tracks relationship health signals, and surfaces relevant connection context when you are visiting a city where contacts live.

GroupCoordinator handles family gathering planning context by pulling together what you know about the group, generates gift suggestions based on known preferences and upcoming dates, maintains awareness of group dynamics including noted conflicts or tensions, and retrieves shared history when you need context before a significant interaction.

RelationshipMemory retrieves what you know about a specific person on demand: the last conversation topic, things they mentioned that were significant, follow-ups you owe them, and a summary of your relationship history across years.

Social Graph across your whole life means: the people who are present from your birth your family, the friendships you form in childhood and school, your professional network as it builds across your career, your romantic relationships, your children if you have them, their networks as they grow, the mentors who shaped you, the colleagues who became friends, and the people you lose to death or distance but whose memory matters to your history. All of it tracked, all of it yours, none of it shared without your consent.

---

# PART 9 — HISTORY GRAPH DOMAIN

The History Graph is the long-term memory of your entire life. It is a personal temporal knowledge graph, a timeline of every significant event in your life, connections between events across domains, and your memories about the people close to you. No other component has a view this complete. Each domain only sees its own records. Only the History Graph and therefore only you see the full picture of your life.

It answers questions like: when did I first deal with this health condition, what was happening in my career when that personal crisis occurred, what do I remember about my father's illness, how has my mental health evolved over the past decade, what were the turning points that led me to my current career, what was I learning when I met my partner.

The most critical design decision is memory attribution. Every memory node has a subject. The subject is either yourself or another person identified by their Social Graph ID. This distinction is permanent and non-negotiable. Memories about others are stored in your History Graph because it is your memory, tagged with the other person's identifier, accessible to you when thinking about that person, never shared with that person without explicit consent, and never used to build a profile of that person.

Memory Node holds: when the event occurred and when it was recorded, an optional period label you assign like college years or Barcelona chapter or Dad's illness, the subject attribution as self or person with relationship context, the domain as health mental-health professional financial relationships education personal-growth family travel creative loss-and-grief achievement or general, an event type within the domain, a short human-readable title, the full encrypted memory content, a confidence score from 0 to 1 for how sure you are it is accurate, the source as self-reported or auto-generated from a domain event or reconstructed or AI-assisted, links to related memories, links to people mentioned, causal links to memories that caused this one and memories this one led to, searchable tags, location, privacy level as private personal close-only or family, a sealed flag meaning this memory is never surfaced in AI context under any circumstances, sentiment as positive negative neutral or complex, and an emotional weight from 0 trivial to 1 life-defining.

Life Chapters are named periods in your life. They can be auto-detected from memory density and major event clusters or manually defined by you. A chapter has a title, start and end dates, a description, the dominant memory domains of that period, and an overall sentiment. Examples are college years, first job in London, Dad's illness, the startup years, the recovery period, new parenthood.

Memory Chains are the most powerful feature. They explicitly link sequences of memories across domains, showing how one life event caused another. The example in the architecture document shows how a parent's cancer diagnosis led to a remote work arrangement which coincided with anxiety and sleep problems which led to starting therapy which ran through the parent's death which eventually led back to office work and then a promotion. This chain is invisible to any single domain. Finance only sees its piece. Health only sees its piece. Only the History Graph shows the full chain. Only you can see how your life actually connected.

Memory Chains have a title, an ordered list of memory nodes, the relationship type between each consecutive pair as caused or led-to or concurrent, and the time span from first to last event with an open end if ongoing.

The events each domain sends to History Graph are:

From Finance: goal achieved, debt paid off, major purchase, income change, financial crisis user-tagged, net worth milestone. No transaction amounts, no balance figures.

From Health: major diagnosis, surgery or procedure, condition resolved, significant medication started, significant fitness milestone like first marathon or weight goal reached, mental health milestone like starting therapy or a recovery milestone. No clinical detail, no scores, no lab values, no medication names.

From Projects: project completed, major milestone reached, project failed or cancelled with user notes, skill demonstrated where you tag what you learned, notable collaboration where you tag the team experience. No task details, no team member personal information.

From Social: relationship formed, significant relationship change, loss through death or distance, reconnection after long absence, relationship health milestone. No interaction details, no personal information about the other person.

The History Graph intelligence agents are:

HistoryScout builds timeline views on request filtered by subject, domain, date range, or life chapter. It detects potential memory chains by finding memories close in time across different domains and suggests linking them. It never forces connections, only suggests them for your confirmation.

HistoryAnalyst runs pattern recognition across years answering questions like what your best professional periods had in common, what life events preceded major career changes, how your relationship with a person evolved over a decade, or what the emotional arc of a particular chapter looks like. It generates grief support timelines showing all your memories about someone who passed. It connects mental health patterns to life context with appropriate privacy protections.

Memory Attribution Enforcer is not an agent but a system rule. Every memory query must specify whether it is self context or other person context. Memories with the sealed flag are never included in AI context under any circumstances. Mental health memories require explicit user invocation through a reflection mode. Memories about others require the relationship context to be specified.

History Graph across your whole life means: birth records entered by your parents or reconstructed later, childhood memories that shape you, educational milestones, the relationships that defined each chapter, the health events that changed your trajectory, the professional decisions that built your career, the losses that left marks, the achievements that defined you, and eventually the final chapter where your records become part of what you leave behind. From birth to death, all of it connected, all of it attributed, all of it private to you.

---

# PART 10 — THE CROSS-DOMAIN BRIDGE

Every data flow between domains passes through a single CrossDomainBridge class. All other cross-domain access raises CrossDomainViolation. This is enforced architecturally, not by convention.

The approved bridges are:

Finance to Digital Twin: finance summary only, containing computed status like financial phase and top goals with progress percentages, no amounts, no account details.

Health to Digital Twin: health status only, a single computed string like managing or good, no conditions, no medications, no lab values.

Projects to Digital Twin: project summary only, containing count of active projects and overdue tasks, no project names unless user has set them as public in their twin, no team member information.

Social to Digital Twin: social summary only, containing count of relationships and upcoming important dates within 30 days, no names, no contact details.

Finance to History Graph: financial events only, the approved event types with date and category but no amounts.

Health to History Graph: health events only, the approved event types with date and sentiment but no clinical details.

Projects to History Graph: professional events only, the approved event types with date and user-set tags but no task details.

Social to History Graph: relationship events only, the approved event types with date but no personal information about the other person.

History Graph to Digital Twin: major life events only, the most recent major event type and date to populate the life context current life major event field.

Social to Projects: team member names and contact hints only, to allow project assignment without leaking personal data about team members.

The CrossDomainBridge implementation validates both the source-target pair and the data type against a whitelist. If either does not match an approved entry, it raises CrossDomainViolation with full details of the attempted violation. This exception is logged as a critical security event.

---

# PART 11 — ENCRYPTION ARCHITECTURE

All user data is end-to-end encrypted. This means encrypted on your device, transmitted encrypted, stored encrypted on the server, and decrypted only for the duration of a single LLM execution window.

The encryption tiers are:

Tier A is end-to-end encrypted with your session key. All Health data, all Finance amounts and account details, all Social contact information and relationship notes, all History Graph memory content. The server never sees plaintext Tier A data except in the controlled decryption window during execution.

Tier B is server-encrypted. System-derived data like knowledge graph nodes, aggregated embeddings, and tool metadata. The server can decrypt this for operations because it is not your private personal data.

Tier C is plaintext. Operational data like execution metadata, routing decisions, cost metrics, and system telemetry. Nothing sensitive is ever in Tier C.

Mental health data is Tier A with an additional sub-key. The sub-key is derived from your User Master Key combined with a mental health salt. Breaking your primary session key does not decrypt mental health records.

The key model uses a User Master Key generated on your device and never transmitted to any server. A Session Key is generated per session, encrypted with your UMK, and sent to the server. The server stores encrypted session key and encrypted data but never your UMK and therefore cannot independently decrypt your data.

The decryption boundary is a single class called ContextDecryptionBoundary. Only this class calls the EncryptionService decrypt method. Decrypted data is used in the execution window and then wiped using ctypes memory zeroing, not Python's garbage collector which does not guarantee immediate memory reclamation.

Rules that are never violated: decrypted data is never persisted, never logged, never cached, never reused across tenants. Logs always show encrypted payload length indicators, never content. Each tenant's keys are completely separate.

---

# PART 12 — AI AGENTS ACROSS YOUR LIFE

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

# PART 13 — LIFE COVERAGE FROM 0 TO 100 PERCENT

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

# PART 14 — STORAGE ARCHITECTURE

Finance domain uses PostgreSQL for accounts, transactions, budgets, goals, and net worth snapshots. Redis caches current balances and budget usage with a one-hour TTL. TimescaleDB handles transaction time series and net worth history for efficient time range queries. All financial amounts are Tier A encrypted. Metadata is Tier B.

Health domain uses PostgreSQL for conditions, medications, and appointments all encrypted. TimescaleDB handles vital signs, mood scores, and fitness entries as time series. An S3-compatible object store with encryption handles medical documents and lab PDFs. Redis caches upcoming appointments and medication reminders. All health data is Tier A. Mental health data has the additional sub-key layer.

Project domain uses PostgreSQL for projects, tasks, milestones, decisions, and notes. Redis caches active project status with a five-minute TTL. Encryption is Tier B since project data is not personal health or finance data, though still private.

Social Graph domain uses Neo4j for person nodes, relationship edges, and group memberships to enable efficient graph traversal for queries like who do I know in this city or how are these two people connected. PostgreSQL handles interaction logs and important dates. Redis caches upcoming important dates. Contact details are Tier A. Relationship metadata is Tier B.

History Graph domain uses Neo4j for memory nodes, chain relationships, and temporal edges. Qdrant stores memory embeddings for semantic search enabling queries like find memories about times I felt lost or memories about my relationship with my father. PostgreSQL handles memory metadata and audit trail. All memory content is Tier A. Mental health memories have the additional sub-key. Redis caches recent memories with a 15-minute TTL.

---

# PART 15 — BUILD SEQUENCE

Phase D1 is foundation running alongside core platform build. This establishes domain isolation enforcement with the CrossDomainBridge and comprehensive tests that verify violations are caught. Digital Twin schema and TwinContext builder are created. Stub twin summaries for all domains are created. The twin update job framework is established.

Phase D2 is Finance domain. Account and Transaction schemas are built. Transaction classification starts rule-based and transitions to ML with user corrections as training signal. Budget management, goal tracking, and net worth calculation are built. Finance to Digital Twin summary interface and Finance to History Graph events are built.

Phase D3 is Health domain. Core health schemas for conditions medications appointments and vitals are built. Fitness entry ingestion from Apple Health, Garmin, and manual entry is built. Vital trend analysis is built. The mental health sub-domain is built with additional encryption and the separate MentalHealthGuardian agent. Health to Digital Twin status summary and Health to History Graph events are built.

Phase D4 is Project Management. Project and Task schemas are built. Milestone tracking and decision recording are built. The project briefing agent, velocity tracking, and deadline risk analysis are built. Strict isolation tests verifying no personal domain access are run.

Phase D5 is Social Graph. Person and Relationship schemas in Neo4j are built. Group management, interaction logging, important date tracking, silence detection, and the consent model implementation are built.

Phase D6 is History Graph. Memory node schema and Neo4j storage are built. The attribution system distinguishing self from other is built. Cross-domain event ingestion from all four domains is built. Timeline builder, chain detection with user confirmation flow, semantic search over memories using Qdrant, and privacy controls including the sealed memory gate and mental health gate are built.

Phase D7 is Digital Twin completion. All domain summaries are connected to the twin updater. Behavioral profile learning from interaction patterns is built. Attention flag generation across all domains is built. TwinContext injection into all agents is verified. Twin version history is completed.

---

# PART 16 — PRIVACY PRINCIPLES THAT ARE NEVER NEGOTIATED

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