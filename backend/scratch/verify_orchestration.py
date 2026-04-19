import asyncio
import uuid
import structlog
from domain.orchestrator.contracts import OrchestratorResult
from core.envelope import ButlerEnvelope
from services.orchestrator.service import OrchestratorService
from unittest.mock import MagicMock, AsyncMock

# Set up logging
structlog.configure()
logger = structlog.get_logger(__name__)

async def test_orchestration_pipeline():
    print("🚀 Starting Orchestration Pipeline Verification...")
    
    # 1. Setup Mocks for dependencies
    mock_db = AsyncMock()
    mock_redis = MagicMock()
    mock_intake = AsyncMock()
    mock_planner = AsyncMock()
    mock_executor = AsyncMock()
    mock_kernel = MagicMock()
    mock_blender = AsyncMock()
    
    # Setup mock returns
    mock_intake.process.return_value = MagicMock(intent="test_intent", mode="chat")
    mock_blender.blend.return_value = []
    mock_planner.create_plan.return_value = MagicMock()
    mock_executor.execute_workflow.return_value = MagicMock(
        content="Hello world", 
        actions=[],
        input_tokens=10,
        output_tokens=20,
        duration_ms=100
    )
    
    # 2. Initialize Orchestrator with CORRECT arguments
    service = OrchestratorService(
        db=mock_db,
        redis=mock_redis,
        intake_proc=mock_intake,
        planner=mock_planner,
        executor=mock_executor,
        kernel=mock_kernel,
        blender=mock_blender
    )
    
    # 3. Process a mock envelope
    envelope = ButlerEnvelope(
        account_id=str(uuid.uuid4()),
        session_id="test_session",
        message="What is the weather in SF?",
        channel="web"
    )

    print("--- Testing Intake ---")
    try:
        # Mock the db commit
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()
        
        result = await service.intake(envelope)
        
        print(f"✅ Intake Completed: WorkflowID={result.workflow_id}")
        print(f"✅ Content Generated: {result.content[:50]}...")
        
        assert isinstance(result, OrchestratorResult)
        assert result.workflow_id is not None
        
    except Exception as e:
        print(f"❌ Orchestration Intake Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n🎉 Orchestration Verification PASSED!")
    return True

if __name__ == "__main__":
    asyncio.run(test_orchestration_pipeline())
