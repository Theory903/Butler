import asyncio
import uuid
from sqlalchemy import select
from infrastructure.database import get_db_context
from domain.orchestrator.models import Workflow, WorkflowEvent, Task

async def check():
    async with get_db_context() as db:
        # Get the last few workflows
        stmt = select(Workflow).order_by(Workflow.created_at.desc()).limit(5)
        res = await db.execute(stmt)
        workflows = res.scalars().all()
        
        for wf in workflows:
            print(f"\nWorkflow {wf.id} ({wf.status})")
            
            # Get events
            ev_stmt = select(WorkflowEvent).where(WorkflowEvent.workflow_id == wf.id).order_by(WorkflowEvent.created_at.asc())
            ev_res = await db.execute(ev_stmt)
            events = ev_res.scalars().all()
            for ev in events:
                print(f"  [{ev.created_at}] Event: {ev.event_type} | Node: {ev.node_id} | Error: {ev.error_data}")
            
            # Get tasks
            task_stmt = select(Task).where(Task.workflow_id == wf.id)
            task_res = await db.execute(task_stmt)
            tasks = task_res.scalars().all()
            for t in tasks:
                print(f"  Task {t.id} ({t.status}) | Tool: {t.tool_name} | Error: {t.error_data}")

if __name__ == "__main__":
    asyncio.run(check())
