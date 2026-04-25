import asyncio
import uuid

from core.deps import get_db, get_redis, get_tools_service
from domain.orchestrator.models import Task, Workflow
from domain.orchestrator.runtime_kernel import ExecutionContext, ExecutionStrategy
from services.orchestrator.backends import ButlerDeterministicExecutor


async def test_det():
    async for db in get_db():
        cache = await get_redis()
        tools = await get_tools_service(db, cache)
        executor = ButlerDeterministicExecutor(tools)

        workflow = Workflow(
            id=uuid.uuid4(),
            account_id=uuid.uuid4(),
            session_id="test",
            plan_schema={"steps": [{"action": "system_stats", "params": {}}]},
        )
        task = Task(
            id=uuid.uuid4(),
            task_type="execution",
            input_data={"query": "stats"},
            workflow_id=workflow.id,
        )

        ctx = ExecutionContext(
            workflow=workflow,
            task=task,
            strategy=ExecutionStrategy.DETERMINISTIC,
            model="cloud-reasoning",
            account_id=str(workflow.account_id),
            session_id=workflow.session_id,
            trace_id="test-trace",
            system_prompt="test",
            messages=[],
            toolset=[],
        )

        try:
            await executor.execute(ctx)
        except Exception:
            import traceback

            traceback.print_exc()
        break


if __name__ == "__main__":
    asyncio.run(test_det())
