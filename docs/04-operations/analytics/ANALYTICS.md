# Analytics and Metrics

> **For:** Product, Engineering, Data Team  
> **Status:** Production Ready  
> **Version:** 2.0  
> **Owner:** Data Team  
> **Last Updated:** 2026-04-16

---

## 1. North Star Metric

| Metric | Definition | Justification |
|--------|------------|---------------|
| **Tasks Completed Successfully** | Total unique tasks (tool executions + direct answers) completed per day | Directly measures Butler's value to users. If users aren't completing tasks, nothing else matters. |

---

## 2. User Lifecycle Metrics

### 2.1 Activation Metrics (Product Team - Weekly)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Signup → Account Created | Users who create account | signups / visitors | >40% | First friction - if low, onboarding flow broken |
| Account → Onboarding Complete | Users finishing onboarding | completed_onboarding / created | >60% | If users drop here, onboarding too complex |
| Onboarding → First Task | Users completing first task | first_task / completed_onboarding | >50% | Critical - if not using, no value realized |
| **Activation Rate** | Signup → First successful task | first_successful_task / signups | >15% | **North star for user activation** |

### 2.2 Engagement Metrics (Product Team - Daily)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| DAU | Unique users with 1+ session | COUNT(DISTINCT user_id) WHERE date=today | 30K | Daily health |
| MAU | Unique users in 30 days | COUNT(DISTINCT user_id) WHERE last_30_days | 100K | Scale health |
| DAU/MAU | Stickiness ratio | DAU / MAU | >30% | <20% = low engagement, >40% = habit-forming |
| Sessions per DAU | Avg sessions per active user | total_sessions / DAU | 3-5 | Indicates usage intensity |
| Tasks per Session | Avg tasks per conversation | total_tasks / total_sessions | 2-4 | Task depth |

### 2.3 Retention Metrics (Product Team - Weekly)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| **D1 Retention** | Users returning day after signup | users_day_1 / signup_cohort | >50% | Immediate value - did they come back? |
| **D7 Retention** | Users returning 7 days after signup | users_day_7 / signup_cohort | >25% | Week-one habit formation |
| **D30 Retention** | Users returning 30 days after signup | users_day_30 / signup_cohort | >15% | Long-term product-market fit |
| **Cohort Retention** | Retention by signup week | D1/D7/D30 by week | Track by cohort | Detect regression by acquisition source |

**Why separate?** D1 catches onboarding issues, D7 catches week-one value, D30 catches long-term fit. Single "retention" number hides problems.

---

## 3. Task Completion Metrics (Product Team - Daily)

### 3.1 Definition of Success

```
SUCCESS = Tool returned valid result AND user did NOT abandon within 30s
PARTIAL = Some steps completed, user requested help or abandoned
FAILURE = Tool error, timeout, or user explicitly marked failed
```

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Task Success Rate | Tasks completed successfully | success / total_tasks | >85% | Core value delivery |
| Task Partial Rate | Tasks with partial completion | partial / total_tasks | <10% | Too high = confusing UX |
| Task Failure Rate | Tasks that failed | failure / total_tasks | <5% | Tool reliability |
| Avg Tasks per User | Tasks completed per active user | total_tasks / DAU | 5-10 | Engagement depth |
| Tasks by Type | Breakdown by task category | COUNT BY task_type | N/A | Feature adoption |

### 3.2 Task Type Breakdown (Product Team - Daily)

| Task Type | Description | Success Target | Notes |
|-----------|-------------|----------------|-------|
| Simple Reply | Direct answer questions | >95% | Lowest friction |
| Tool Action | Single tool execution | >85% | Core value |
| Multi-Step Workflow | Automation workflows | >70% | Higher complexity |
| Search/RAG | Information retrieval | >80% | Quality dependent |
| Voice Input | Speech-to-text tasks | >85% | STT accuracy dependent |
| Vision Input | Image analysis tasks | >75% | OCR/understanding dependent |

---

## 4. Performance Metrics (Engineering Team - Real-time)

### 4.1 Latency by Endpoint (Engineering Team - Real-time)

| Endpoint | P50 | P95 | P99 | Owner | Justification |
|----------|-----|-----|-----|-------|---------------|
| POST /chat (simple) | 200ms | 500ms | 800ms | Gateway | Direct response path |
| POST /chat (action) | 300ms | 800ms | 1.5s | Orchestrator | Tool execution |
| POST /chat (workflow) | 500ms | 2s | 5s | Orchestrator | Multi-step |
| GET /search | 150ms | 400ms | 800s | Search | RAG pipeline |
| POST /voice/process | 500ms | 1.5s | 3s | Audio | STT + processing |
| POST /vision/analyze | 800ms | 2s | 4s | Vision | OCR + analysis |
| WS /realtime | 100ms | 300ms | 500ms | Realtime | WebSocket latency |

### 4.2 Error Rate Definition (Engineering Team - Real-time)

| Error Type | Definition | Includes | Excludes |
|------------|------------|----------|----------|
| **Tool Error** | Tool execution failed | API failures, auth errors, invalid params | User errors in input |
| **Timeout** | Request exceeded limit | All timeouts (30s gateway, 60s tool) | N/A |
| **Model Error** | LLM returned error | Rate limits, invalid response, parsing | Content quality issues |
| **User-Visible Error** | User saw error message | Any error shown to user | Silent failures |
| **Total Error Rate** | All failures | All above | Retries, idempotent duplicates |

**Target:** Total error rate <1%, User-visible error <0.5%

### 4.3 Reliability Metrics (Engineering Team - Real-time)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Uptime | Service availability | (total_time - downtime) / total_time | >99.9% | Basic reliability |
| SLO Compliance | 99.9% of requests within latency | requests_within_SLO / total | >99.9% | Commit to users |
| SLA Compliance | Contractual uptime | Per SLA terms | >99.5% | Legal commitment |
| Incident Count | Production incidents | COUNT(incident_id) | <2/week | Operational health |
| MTTR | Mean time to resolution | AVG(resolve_time - detect_time) | <30min | Incident handling |

---

## 5. AI Quality Metrics (ML Team - Daily)

### 5.1 Intent Classification (ML Team - Daily)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Intent Accuracy | Correct intent classification | correct_intent / total_classified | >90% | Core understanding |
| Top-3 Intent Accuracy | Correct in top 3 guesses | correct_top3 / total | >95% | User-friendly fallback |
| Clarification Rate | Intent too uncertain to proceed | unclear / total | <10% | Too high = confusing users |
| Confidence Distribution | Histogram of confidence scores | BY confidence_bucket | N/A | Calibration check |

### 5.2 Tool Execution (ML Team - Daily)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Tool Success Rate | Tools executed without error | tool_success / tool_called | >90% | Tool reliability |
| Tool Relevance | Tool matches user intent | human_rated_relevant / sampled | >85% | Correct tool selected |
| Parameter Accuracy | Correct params extracted | correct_params / total_params | >88% | Understanding details |

### 5.3 Response Quality (ML Team - Weekly)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Hallucination Rate | Factual errors in responses | errors / total_responses | <2% | Trust killer |
| Citation Accuracy | Sources actually contain info | verified / citations | >90% | RAG quality |
| Response Relevance | Response matches query | human_rated / sampled | >85% | Helpfulness |
| User Rating | Thumbs up/down ratio | thumbs_up / total_ratings | >70% | Direct feedback |

---

## 6. Memory Metrics (ML Team - Daily)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Retrieval Hit Rate | Memory returns useful info | useful / retrieval_calls | >75% | Memory value |
| Context Quality | Retrieved context relevant | human_rated / sampled | >80% | Retrieval quality |
| Retrieval Latency | Time to get context | AVG( retrieval_time_ms) | <50ms | Performance |
| Memory Write Latency | Time to store | AVG( write_time_ms) | <20ms | Performance |
| Context Length | Avg tokens in context | AVG( tokens ) | 2000-4000 | Budget compliance |

---

## 7. Search/RAG Metrics (ML Team - Daily)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Search Relevance | Results match query | relevant_results / total_results | >80% | Quality |
| Citation Accuracy | Citations contain claim | verified / total_citations | >90% | Truthfulness |
| Stale Result Rate | Outdated info returned | stale / total_results | <5% | Freshness |
| Zero Result Rate | No results found | zero_results / queries | <10% | Coverage |
| RAG Latency | End-to-end search time | AVG(search_time_ms) | <300ms | Performance |

---

## 8. Voice/Vision Metrics (ML Team - Daily)

### 8.1 Voice (Speech-to-Text)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| STT Accuracy | Words correctly transcribed | correct_words / total_words | >92% | Core quality |
| Wake Word False Trigger | Accidental activation | false_triggers / day | <3 | Annoyance |
| STT Latency | Time to transcription | AVG(latency_ms) | <500ms | Real-time |
| Unsupported Language | Language not recognized | unsupported / total | <5% | Coverage |

### 8.2 Vision (Image Analysis)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| OCR Accuracy | Text correctly extracted | correct_chars / total_chars | >90% | Core quality |
| Object Detection | Objects correctly identified | correct / total_objects | >85% | Understanding |
| Image Analysis Quality | Analysis matches image | human_rated / sampled | >80% | Usefulness |

---

## 9. Workflow Metrics (Product Team - Daily)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Workflow Success | All steps completed | success / total_workflows | >75% | Automation value |
| Workflow Partial | Some steps completed | partial / total | <15% | Failure detection |
| Workflow Drop-off | User abandoned mid-workflow | abandoned / started | <10% | UX friction |
| Avg Steps per Workflow | Steps in completed workflows | AVG(steps) | 3-8 | Complexity |
| Retry Rate | Workflows requiring retry | retry / total | <10% | Reliability |
| Automation Active | User automations running | active / created | >60% | Value realized |

---

## 10. Recommendation Metrics (ML Team - Daily)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Suggestion CTR | Click through suggestions | clicks / shown | >15% | Relevance |
| Suggestion Acceptance | User used suggestion | accepted / clicked | >40% | Quality |
| Suggestion Success | Accepted suggestion worked | success / accepted | >80% | Value |
| Recommendation Diversity | Unique suggestions per user | unique / total | >30% | Not repetitive |

---

## 11. Business Metrics (Growth/Finance Team - Monthly)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| **CAC** | Cost to acquire customer | total_acquisition_cost / new_customers | <$15 | Efficiency |
| **LTV** | Lifetime value of customer | avg_revenue_per_user * lifetime | >$120 | Unit economics |
| LTV/CAC Ratio | Efficiency ratio | LTV / CAC | >8 | Health |
| **Conversion Rate** | Free → Paid | paid / total_users | >5% | Monetization |
| Paid Retention | Paid users continuing | paid_month_2 / paid_month_1 | >80% | Churn |
| ARPU | Average revenue per user | revenue / total_users | >$5/month | Revenue |
| MRR | Monthly recurring revenue | SUM(paid_users * price) | Growth | Scale |

**Note:** These metrics require monetization to be live. Track funnel before monetization.

---

## 12. Infrastructure Metrics (Engineering Team - Real-time)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| RPS by Service | Requests per second per service | COUNT / second | Per service | Load |
| Queue Lag | Messages waiting | AVG(wait_time_ms) | <100ms | Responsiveness |
| DB Latency (Read) | PostgreSQL read query time | AVG(read_ms) | <50ms | Performance |
| DB Latency (Write) | PostgreSQL write query time | AVG(write_ms) | <100ms | Performance |
| Cache Hit Rate | Redis cache effectiveness | hits / (hits+misses) | >90% | Efficiency |
| Worker Backlog | Queued but not processed | COUNT(pending) | <100 | Capacity |
| API Error Rate | 5xx errors from services | errors / requests | <0.1% | Health |

---

## 13. Cost Metrics (Finance/Engineering Team - Daily)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Cost per Request | Total cost / total requests | $0.001-0.01 | Per request | Efficiency |
| Cost per Active User | Total cost / DAU | $0.05-0.20 | Per user | Unit economics |
| Model Spend | LLM API costs | Monthly total | Track | Budget |
| Infrastructure Spend | Compute + storage | Monthly total | Track | Budget |
| Tool API Spend | External tool costs | Monthly total | Track | Budget |

---

## 14. Security Analytics (Security Team - Real-time)

| Metric | Definition | Formula | Target | Justification |
|--------|------------|---------|--------|---------------|
| Suspicious Actions | Anomalous user behavior | COUNT(anomaly) | <10/day | Security |
| Permission Denials | Blocked by policy | denied / total_attempts | Track | Policy health |
| Audit Anomalies | Unusual audit patterns | COUNT(anomaly) | <5/day | Compliance |
| Failed Auth | Login failures | failures / attempts | <5% | Security |
| MFA Adoption | Users with MFA enabled | mfa_enabled / total | >50% | Security |

---

## 15. Segmentation (All Teams - Daily)

| Dimension | Segments | Purpose |
|-----------|----------|---------|
| Platform | iOS, Android, Web | Product optimization |
| Region | US, EU, APAC, Other | Localization |
| User Type | Free, Trial, Paid | Monetization |
| Device Tier | High, Mid, Low | Performance |
| Feature | Voice, Text, Automation | Adoption |

---

## 16. Funnel Metrics (Product Team - Daily)

### 16.1 First-Run UX Funnel

| Step | Metric | Target | Drop-off |
|------|--------|-------|----------|
| App Open | users_opened_app | 100% | - |
| Onboarding Start | started_onboarding | >80% | <20% |
| Onboarding Complete | completed_onboarding | >60% | <25% |
| First Task Attempt | attempted_first_task | >50% | <20% |
| First Task Success | completed_first_task | >40% | <15% |

### 16.2 Automation Creation Funnel

| Step | Metric | Target | Drop-off |
|------|--------|-------|----------|
| View Automations | viewed_automation_tab | N/A | - |
| Create Click | clicked_create | >20% | - |
| Save Automation | saved_automation | >40% | - |
| Run Automation | ran_automation | >60% | - |
| Success | automation_worked | >70% | - |

---

## 17. Dashboards

### 17.1 Dashboard Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DASHBOARD LAYER                                     │
├──────────────────┬──────────────────┬──────────────────┬─────────────────────────┤
│   Executive      │   Product        │    ML Quality    │      Engineering       │
│   (C-Suite)      │   (PM/Design)    │    (ML Team)     │      (Eng/SRE)        │
├──────────────────┼──────────────────┼──────────────────┼─────────────────────────┤
│ - DAU/MAU        │ - Activation     │ - Intent accuracy│ - P50/P95/P99          │
│ - Retention      │ - Task success   │ - Tool success   │ - Error rate           │
│ - Revenue        │ - Funnel         │ - Hallucination  │ - Uptime/SLO           │
│ - Growth         │ - Segmentation   │ - Retrieval      │ - RPS/Queue            │
│                  │ - Features       │ - Latency       │ - Infra               │
└──────────────────┴──────────────────┴──────────────────┴─────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                          │
├─────────────────────────────────────────────────────────────────────────────────┤
│  Primary:  Event Pipeline (not PostgreSQL!)                                      │
│  - ClickHouse / Snowflake / BigQuery for analytics                               │
│  - Kafka for event stream                                                        │
│  - Redis for real-time (last 24h)                                                │
│  - PostgreSQL for transactional only                                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│  Secondary: Operational                                                          │
│  - Prometheus (metrics)                                                          │
│  - Grafana (visualization)                                                       │
│  - Sentry (errors)                                                               │
│  - Datadog (APM)                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 17.2 Dashboard Details

| Dashboard | Primary Source | Refresh | Audience |
|-----------|---------------|---------|----------|
| Executive | Snowflake + Stripe | Daily 8am | C-Suite |
| Product | Snowflake + Event API | Hourly | PM, Design |
| ML Quality | Snowflake + Custom | Daily | ML Team |
| Engineering | Prometheus + Grafana | Real-time | Eng, SRE |
| Growth | Snowflake + Stripe | Daily | Growth Team |
| Security | Custom + Audit logs | Real-time | Security |

---

## 18. Alerts

### 18.1 Severity Levels

| Severity | Definition | Response Time | Examples |
|----------|------------|---------------|----------|
| **P1 - Critical** | Service down or data loss | <15 min | Service down, >10% error rate |
| **P2 - High** | Major feature broken | <1 hour | Task success <70%, latency P99 >10s |
| **P3 - Medium** | Minor feature affected | <4 hours | Error rate >3%, latency >SLO |
| **P4 - Low** | Cosmetic or warning | <24 hours | Deprecation, minor anomalies |

### 18.2 Alert Rules with Runbooks

| Alert | Condition | Severity | Runbook | Action |
|-------|-----------|----------|---------|--------|
| Service Down | Any service returns 503 | P1 | [runbooks/service-down.md](../runbooks/service-down.md) | Page on-call |
| High Error Rate | >5% errors for 5min | P1 | [runbooks/high-latency.md](../runbooks/high-latency.md) | Page on-call |
| Latency P99 | >3s for 5min | P2 | [runbooks/high-latency.md](../runbooks/high-latency.md) | Investigate |
| Task Success | <70% for 1 hour | P2 | [runbooks/service-down.md](../runbooks/service-down.md) | Page on-call |
| DB Latency | >200ms for 5min | P2 | [runbooks/database-failure.md](../runbooks/database-failure.md) | Investigate |
| Queue Lag | >1000 messages | P3 | [runbooks/high-latency.md](../runbooks/high-latency.md) | Check workers |
| Cache Hit Rate | <70% | P3 | - | Investigate |
| High Memory | >80% usage | P3 | [runbooks/service-down.md](../runbooks/service-down.md) | Scale |
| Retention Drop | D7 <20% (vs 7-day avg) | P3 | - | Product review |
| Suspicious Activity | >10x normal | P2 | [security/SECURITY.md](../security/SECURITY.md) | Security review |

### 18.3 Alert Threshold Design

**Critical Issue Fixed:** Alert at 5%, target is <1%. Now:
- Alert threshold: 3% (3x target, not 5x)
- Warning threshold: 1.5% (1.5x target)
- Clear when: <0.8%

---

## Summary of Changes (v1 → v2)

| Area | Before | After |
|------|--------|-------|
| Targets | Random numbers | Owned + timeframe + justification |
| Business metrics | CAC, LTV without context | Full context + when to track |
| Activation | None | Signup → onboarding → first task |
| Usage | None | Tasks per user, sessions per day |
| Retention | Single number | D1, D7, D30 by cohort |
| Performance | Global P50/P95/P99 | By endpoint + task type |
| Errors | "<1%" vague | Tool/timeout/model/user-visible defined |
| Task success | Vague | SUCCESS/PARTIAL/FAILURE defined |
| AI quality | None | Intent, tool, hallucination rates |
| Workflow | None | Success, partial, retry, drop-off |
| Memory | None | Hit rate, quality, latency |
| Recommendations | None | CTR, acceptance, success |
| Search/RAG | None | Relevance, citation, staleness |
| Voice/Vision | None | STT accuracy, wake-word, OCR |
| Business (monetization) | CAC/LTV early | Conversion, paid retention first |
| Dashboards | 3 shallow | 6 detailed with proper sources |
| Data source | PostgreSQL | Event pipeline + warehouse |
| Alerts | Loose | Severity levels + runbook links |
| Infra | None | RPS, queue, DB, cache, workers |
| Reliability | None | Uptime, SLO, SLA, incidents |
| Cost | None | Per request, per user, by category |
| Security | None | Suspicious actions, denials, anomalies |
| Segmentation | None | Platform, region, user type, device |
| Funnel | None | First-run, automation creation |
| North star | None | Tasks completed successfully |

---

*Document owner: Data Team*  
*Version: 2.0 - Production Ready*  
*Last updated: 2026-04-16*