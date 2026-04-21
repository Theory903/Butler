
import asyncio
import uuid
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from redis.asyncio import Redis

from core.config import settings
from domain.orchestrator.models import Workflow, Task
from domain.orchestrator.workflow_dag import WorkflowDAG, DAGNode
from services.orchestrator.executor import DurableExecutor
from services.orchestrator.planner import Plan, Step
from core.deps import (
    get_runtime_kernel,
    get_memory_service,
    get_tools_service,
    get_task_state_machine,
    get_lock_manager,
    get_blender,
    get_smart_router,
    get_feature_service,
    get_redaction_service,
    get_content_guard
)

async def diag():
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    redis = Redis.from_url(settings.REDIS_URL)
    
    async with async_session() as db:
        # 1. Create a dummy workflow and plan
        workflow_id = uuid.uuid4()
        account_id = uuid.UUID("56067a87-06c6-41b5-9564-4452c0344000")
        
        # Simple plan: one web_search node
        plan_dict = {
            "nodes": [
                {
                    "id": "node_1",
                    "kind": "task",
                    "tool_name": "search_web",
                    "inputs": {"query": "latest AI news"},
                    "next_nodes": []
                }
            ],
            "edges": []
        }
        
        workflow = Workflow(
            id=workflow_id,
            account_id=account_id,
            session_id="diag_session_" + uuid.uuid4().hex[:8],
            intent="news",
            mode="durable",
            status="active",
            plan_schema=plan_dict
        )
        db.add(workflow)
        await db.flush()
        
        plan = Plan(steps=[Step(action="search_web", params={"query": "latest AI news"})])
        
        # 2. Get dependencies
        kernel = await get_runtime_kernel()
        memory = await get_memory_service()
        tools = await get_tools_service()
        sm = get_task_state_machine()
        locks = get_lock_manager()
        blender = await get_blender()
        router = await get_smart_router()
        features = await get_feature_service()
        redaction = await get_redaction_service()
        safety = await get_content_guard()
        
        executor = DurableExecutor(
            db=db,
            redis=redis,
            kernel=kernel,
            memory_service=memory,
            tools_service=tools,
            state_machine=sm,
            lock_manager=locks,
            blender=blender,
            smart_router=router,
            feature_service=features,
            redaction_service=redaction,
            safety_service=safety,
            model="groq/llama-3.3-70b-versatile"
        )
        
        print(f"--- Starting diagnostic execution for workflow {workflow_id} ---")
        try:
            result = await executor.execute_workflow(workflow, plan)
            print(f"SUCCESS: Result content: {result.content}")
            print(f"Metadata: {result.metadata}")
        except Exception as e:
            import traceback
            print(f"FAILURE: {str(e)}")
            traceback.print_exc()
        finally:
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(diag())
