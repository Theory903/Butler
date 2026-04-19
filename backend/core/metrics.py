from opentelemetry import metrics

meter = metrics.get_meter("butler")

# --- Workflow Metrics ---
workflow_started = meter.create_counter(
    "butler.workflow.started_total",
    description="Total workflows started",
)
workflow_completed = meter.create_counter(
    "butler.workflow.completed_total",
    description="Total workflows completed successfully",
)
workflow_failed = meter.create_counter(
    "butler.workflow.failed_total",
    description="Total workflows failed",
)
workflow_duration = meter.create_histogram(
    "butler.workflow.duration_seconds",
    description="Workflow execution duration",
    unit="s",
)

# --- Tool Metrics ---
tool_calls = meter.create_counter(
    "butler.tool.calls_total",
    description="Total tool invocations",
)
tool_duration = meter.create_histogram(
    "butler.tool.duration_seconds",
    description="Tool execution duration",
    unit="s",
)

# --- Intent Metrics ---
intent_classified = meter.create_counter(
    "butler.intent.classified_total",
    description="Total intents classified",
)
intent_duration = meter.create_histogram(
    "butler.intent.classification_duration_seconds",
    description="Intent classification latency",
    unit="s",
)

# --- LLM Metrics ---
llm_tokens = meter.create_counter(
    "butler.llm.tokens_total",
    description="Total LLM tokens consumed",
)

# --- Security Metrics ---
injection_suspected = meter.create_counter(
    "ai_security.prompt_injection_suspected_total",
    description="Suspected prompt injection attempts",
)
tool_blocked = meter.create_counter(
    "ai_security.tool_request_blocked_total",
    description="Tool requests blocked by policy",
)
