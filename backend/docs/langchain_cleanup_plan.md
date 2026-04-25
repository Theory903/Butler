# LangChain Integration Cleanup Plan (Phase 13)

## Objective
Remove direct LangChain dependencies and replace with Butler-owned abstractions.

## Current LangChain Usage (from Phase 0.5 scan)
- Direct imports: 64 files with LangChain imports
- Locations: services/ml_runtime/, services/agent/, domain/agent/

## Migration Strategy

### Step 1: Create Butler-owned abstractions
- `domain/llm/protocol.py` - Butler LLM protocol
- `domain/llm/provider.py` - Provider abstraction (OpenAI, Anthropic)
- `domain/llm/message.py` - Message types (User, Assistant, Tool)

### Step 2: Replace LangChain message types
- Replace `HumanMessage` with `UserMessage`
- Replace `AIMessage` with `AssistantMessage`
- Replace `ToolMessage` with `ToolResultMessage`

### Step 3: Replace LangChain tool calls
- Replace LangChain tool schemas with ToolSpec
- Replace LangChain tool execution with ToolResultEnvelope

### Step 4: Replace LangChain chains
- Replace LangChain chains with Butler workflows
- Use Temporal for durable workflow execution

### Step 5: Remove LangChain dependencies
- Remove `langchain` from requirements.txt
- Remove `langchain-openai` from requirements.txt
- Remove `langchain-anthropic` from requirements.txt

## Validation
- All LangChain imports removed
- All LangChain types replaced
- Tests pass with new abstractions
