import pytest
import uuid
import json
from unittest.mock import AsyncMock, MagicMock
from services.memory.graph_extraction import KnowledgeExtractionEngine
from domain.memory.models import KnowledgeEntity

@pytest.mark.asyncio
async def test_extraction_engine_calls_llm_and_stores():
    # Setup Mocks
    embedder = AsyncMock()
    embedder.embed.return_value = [0.1] * 1536
    
    neo4j_repo = AsyncMock()
    # Mock upsert_entity to return a real KnowledgeEntity object
    mock_entity = KnowledgeEntity(
        id=uuid.uuid4(),
        account_id=uuid.uuid4(),
        entity_type="Person",
        name="Alice",
        summary="User's best friend"
    )
    neo4j_repo.upsert_entity.return_value = mock_entity
    
    ml_runtime = AsyncMock()
    mock_llm_response = {
        "generated_text": json.dumps({
            "entities": [
                {
                    "name": "Alice", 
                    "type": "Person", 
                    "summary": "User's best friend",
                    "is_explicit": True,
                    "confidence": 1.0
                }
            ],
            "relations": []
        })
    }
    ml_runtime.execute_inference.return_value = mock_llm_response
    
    engine = KnowledgeExtractionEngine(
        embedder=embedder,
        neo4j_repo=neo4j_repo,
        ml_runtime=ml_runtime
    )
    
    # Execute
    account_id = str(uuid.uuid4())
    text = "Alice is my best friend."
    source_id = uuid.uuid4()
    
    result = await engine.extract_and_store(
        account_id=account_id,
        text=text,
        source_id=source_id,
        source_type="episode"
    )
    
    # Assertions
    assert len(result) == 1
    ml_runtime.execute_inference.assert_called_once()
    neo4j_repo.upsert_entity.assert_called_once()
    neo4j_repo.store_chunk.assert_called_once()
    
    # Verify entity ids were passed to store_chunk
    args, kwargs = neo4j_repo.store_chunk.call_args
    assert kwargs["entity_ids"] == [mock_entity.id]
    assert kwargs["source_id"] == source_id
