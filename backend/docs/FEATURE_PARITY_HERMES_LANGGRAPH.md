# Feature Parity: HermesAgentBackend → LangGraphAgentBackend

This document maps all features from the legacy HermesAgentBackend to the new LangGraphAgentBackend to ensure no functionality is degraded during the migration.

## Feature Parity Matrix

| Feature | HermesAgentBackend | LangGraphAgentBackend | Status | Notes |
|---------|-------------------|----------------------|--------|-------|
| **Core Execution** | | | | |
| Single-step agent decision | ✓ `_decide()` | ✓ LangGraph multi-turn | ✅ Implemented | LangGraph provides multi-turn with built-in synthesis |
| Tool execution | ✓ `_execute_tool_from_decision()` | ✓ ButlerLangChainTool | ✅ Implemented | Hybrid governance (L0/L1 direct, L2/L3 via ToolExecutor) |
| Message normalization | ✓ `_normalize_messages()` | ✓ `_normalize_messages()` in adapter | ✅ Implemented | Identical behavior |
| Conversation history handling | ✓ `_build_prompt()` | ✓ via LangGraph messages | ✅ Implemented | LangGraph handles history natively |
| **Streaming** | | | | |
| Stream tokens | ✓ `_chunk_text()` + StreamTokenEvent | ✓ LangChainEventAdapter | ✅ Implemented | Adapter maps LC events to Butler events |
| Stream final event | ✓ StreamFinalEvent | ✓ StreamFinalEvent | ✅ Implemented | Same event schema |
| Configurable chunk size | ✓ `stream_chunk_size` parameter | ✓ `stream_chunk_size` parameter | ✅ Implemented | Passed through to backend |
| **ML Integration** | | | | |
| ML runtime delegation | ✓ IReasoningRuntime | ✓ ButlerChatModel → MLRuntimeManager | ✅ Implemented | Preserves Butler's model routing |
| Default reasoning tier | ✓ `default_tier` parameter | ✓ `default_tier` parameter | ✅ Implemented | T2 default for both |
| Model selection | ✓ `preferred_model` | ✓ `preferred_model` | ✅ Implemented | Supports per-request model override |
| **Governance** | | | | |
| Tool governance | ✓ ToolExecutor | ✓ ButlerLangChainTool hybrid | ✅ Implemented | L0/L1: direct dispatch, L2/L3: governed execution |
| Approval interrupts | ✓ via ToolExecutor | ✓ via ToolExecutor (L2/L3) | ✅ Implemented | Same approval flow |
| Audit logging | ✓ ToolExecutor | ✓ ToolExecutor | ✅ Implemented | Reuses Butler's audit trail |
| **Multi-tenancy** | | | | |
| Tenant context | ✓ ExecutionContext.tenant_id | ✓ AgentRequest.tenant_id | ✅ Implemented | Propagated via ButlerToolRuntime |
| Account context | ✓ ExecutionContext.account_id | ✓ AgentRequest.account_id | ✅ Implemented | Propagated via ButlerToolRuntime |
| Session context | ✓ ExecutionContext.session_id | ✓ AgentRequest.session_id | ✅ Implemented | Propagated via ButlerToolRuntime |
| Trace context | ✓ ExecutionContext.trace_id | ✓ AgentRequest.trace_id | ✅ Implemented | Propagated via ButlerToolRuntime |
| User context | ✓ ExecutionContext.user_id | ✓ AgentRequest.user_id | ✅ Implemented | Propagated via ButlerToolRuntime |
| **Response Format** | | | | |
| Content field | ✓ `response.content` | ✓ `response.content` | ✅ Implemented | Same field name |
| Actions/tool calls | ✓ `actions: []` | ✓ `tool_calls: []` | ✅ Implemented | Mapped in adapter |
| Duration tracking | ✓ `duration_ms` | ✓ `duration_ms` in usage | ✅ Implemented | Same metric |
| **Error Handling** | | | | |
| Tool execution errors | ✓ ToolExecutor | ✓ ToolExecutor | ✅ Implemented | Same error flow |
| ML runtime errors | ✓ IReasoningRuntime | ✓ ButlerChatModel | ✅ Implemented | Same error handling |
| Streaming errors | ✓ yields events | ✓ yields error events | ✅ Implemented | StreamErrorEvent for failures |
| **Advanced Features** | | | | |
| Checkpointing | ✗ Not supported | ✓ Postgres checkpointing | ✨ Enhanced | LangGraph adds durability |
| Multi-turn synthesis | ✗ Concatenates response + tool output | ✓ Built-in synthesis turn | ✨ Enhanced | Fixes raw tool output issue |
| Event streaming | ✓ Butler events only | ✓ LC events → Butler events | ✅ Implemented | Adapter preserves Butler schema |

## Implemented Enhancements

The LangGraph backend includes several enhancements over Hermes:

1. **Postgres Checkpointing**: Durable state persistence across process restarts
2. **Built-in Synthesis Turn**: LangGraph automatically synthesizes tool outputs instead of simple concatenation
3. **Multi-turn Capability**: Can handle multiple tool calls in sequence with intermediate reasoning
4. **LangGraph Ecosystem**: Access to LangGraph's workflow patterns, supervisor, and A2A capabilities

## Migration Path

### Feature Flag Control

```bash
# Use new LangGraph backend (default)
export BUTLER_AGENT_RUNTIME=langgraph

# Fall back to Hermes backend
export BUTLER_AGENT_RUNTIME=legacy
```

### Interface Compatibility

Both backends implement the same interface via the adapter pattern:

```python
async def run(ctx: ExecutionContext) -> dict[str, Any]:
    """Returns: {content, actions, duration_ms}"""

async def run_streaming(ctx: ExecutionContext) -> AsyncGenerator[ButlerEvent]:
    """Yields: StreamTokenEvent, StreamFinalEvent, StreamErrorEvent, etc."""
```

## Testing Recommendations

1. **Unit tests**: Test both backends with identical inputs, verify output format matches
2. **Integration tests**: Test tool execution with L0/L1/L2/L3 tiers
3. **Streaming tests**: Verify event sequence matches between backends
4. **Multi-tenancy tests**: Verify context propagation for tenant/account/session
5. **Error handling tests**: Verify error events are emitted correctly

## Status Summary

- **✅ Implemented**: All core features from Hermes are available in LangGraph
- **✨ Enhanced**: LangGraph provides additional capabilities (checkpointing, synthesis)
- **✗ Degraded**: None - feature parity maintained

The LangGraph backend is feature-complete with the legacy Hermes backend and provides additional capabilities for future workflow patterns.
