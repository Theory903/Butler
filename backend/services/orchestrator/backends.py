import asyncio
import os
import structlog
from typing import Any, AsyncGenerator

from domain.orchestrator.runtime_kernel import ExecutionContext, ExecutionStrategy
from domain.events.schemas import ButlerEvent, StreamTokenEvent

logger = structlog.get_logger(__name__)

class ButlerDeterministicExecutor:
    """Executes single tool calls directly without LLM reasoning."""

    def __init__(self, tools_service):
        self._tools = tools_service

    async def execute(self, ctx: ExecutionContext) -> dict:
        plan = getattr(ctx.workflow, "plan_schema", {}) or {}
        steps = plan.get("steps", [])
        
        if not steps:
            return {"content": "No steps to execute deteministically", "actions": [], "duration_ms": 0}

        # For deterministic, we only execute the FIRST step that isn't response
        step = steps[0]
        action = step.get("action")
        params = step.get("params", {})

        logger.info("deterministic_execution_start", action=action, task_id=str(ctx.task.id))
        
        result = await self._tools.execute(
            tool_name=action,
            params=params,
            account_id=ctx.account_id,
            task_id=str(ctx.task.id),
            session_id=ctx.session_id,
        )

        return {
            "content": f"System Diagnosis:\n{result.data}",
            "actions": [result.dict()],
            "requires_approval": False,
            "duration_ms": 0
        }


class HermesAgentBackend:
    """Agentic LLM bridge that uses MLRuntimeManager to reason and ToolsService to act."""

    def __init__(self, ml_runtime, tools_service):
        self._ml = ml_runtime
        self._tools = tools_service

    async def run(self, ctx: ExecutionContext) -> dict:
        # Simple non-streaming wrapper around run_streaming for now
        content = ""
        async for event in self.run_streaming(ctx):
            if isinstance(event, StreamTokenEvent):
                content += event.payload.get("content", "")
        
        return {
            "content": content,
            "actions": [], # Actions would be parsed from trajectory if we had it
            "duration_ms": 0
        }

    async def run_streaming(self, ctx: ExecutionContext) -> AsyncGenerator[ButlerEvent, None]:
        """A simple iterative loop: Reasoning -> Tool Call -> Observation -> Final Response.
        
        This is a lightweight version of the full Hermes loop, suitable for local activation.
        """
        # FIX: Use messages from context instead of task.message (Task has no message field)
        task_msg = ""
        if ctx.messages:
            # Use user message from context.messages (contains node inputs)
            user_msgs = [m["content"] for m in ctx.messages if m.get("role") == "user"]
            task_msg = user_msgs[0] if user_msgs else ""
        prompt = f"{ctx.system_prompt}\n\nCurrent Task: {task_msg}"
        if ctx.messages:
            prompt += "\n\nHistory:\n" + "\n".join([f"{m['role']}: {m['content']}" for m in ctx.messages if m.get("role") != "user"])

        # Step 1: Reasoning + Tool Selection
        # In this simple bridge, we pass the available tool specs to the prompt
        tool_desc = "\n".join([f"- {s.name}: {s.description}" for s in ctx.toolset])
        prompt += f"\n\nAvailable Tools:\n{tool_desc}\n\nThink carefully and call a tool if needed using <tool_call>name(params)</tool_call> format."

        # Since we are wrapping a simple ML runtime, we do a one-shot or 2-turn loop here
        # For 'system_stats', the planner ALREADY created a plan, so we might just execute it.
        # But for 'macro' mode, we let the LLM decide.

        import structlog
        logger = structlog.get_logger(__name__)
        
        # FIX: Resolve correct profile name from ctx.model
        # ctx.model can be "qwen/qwen3-32b", "groq/llama-3.3-70b-versatile", etc.
        user_model = ctx.model or os.environ.get("DEFAULT_MODEL", "groq/llama-3.3-70b-versatile")
        if user_model and "/" in user_model:
            provider = user_model.split("/")[0].lower()
            profile_name = f"cloud-{provider}"
        else:
            profile_name = "cloud-groq"  # Safe default
        
        logger.warning("HERMES_BACKEND_DEBUG", 
            prompt=prompt[:200], 
            system_prompt=ctx.system_prompt[:100] if ctx.system_prompt else "",
            has_messages=bool(ctx.messages),
            messages=ctx.messages,
            user_model=user_model,
            resolved_profile=profile_name
        )
        
        inference_result = await self._ml.execute_inference(
            profile_name=profile_name,
            payload={"prompt": prompt, "system_prompt": ctx.system_prompt}
        )

        logger.warning("HERMES_BACKEND_RESULT", result=inference_result)
        content = inference_result.get("content", "")
        
        # 2. Yield tokens (simulated)
        for chunk in [content[i:i+20] for i in range(0, len(content), 20)]:
            yield StreamTokenEvent(
                account_id=ctx.account_id,
                session_id=ctx.session_id,
                task_id=str(ctx.task.id),
                trace_id=ctx.trace_id,
                payload={"content": chunk}
            )
            await asyncio.sleep(0.01)
