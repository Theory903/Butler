import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from domain.memory.notebook_models import Notebook, Source, Note
from services.memory.notebook_repo import PostgresNotebookRepository
from services.memory.transformation_service import TransformationService
from core.deps import get_db

router = APIRouter(prefix="/research", tags=["research"])

class NotebookCreate(BaseModel):
    title: str
    description: Optional[str] = None

class SourceCreate(BaseModel):
    notebook_id: str
    url: str
    title: Optional[str] = None

@router.post("/notebooks")
async def create_notebook(data: NotebookCreate, repo: PostgresNotebookRepository = Depends(get_db)):
    # Mocking account_id for now as is consistent with other routes
    account_id = str(uuid.uuid4()) 
    return await repo.create_notebook(account_id=account_id, title=data.title, description=data.description)

@router.get("/notebooks")
async def list_notebooks(repo: PostgresNotebookRepository = Depends(get_db)):
    account_id = str(uuid.uuid4())
    return await repo.list_notebooks(account_id)

@router.post("/sources")
async def add_source(data: SourceCreate, repo: PostgresNotebookRepository = Depends(get_db), transformer: TransformationService = Depends()):
    # 1. Ingest content based on URL
    if "youtube.com" in data.url or "youtu.be" in data.url:
        ingest_result = await transformer.ingest_youtube(data.url)
    else:
        ingest_result = await transformer.ingest_url(data.url)
        
    if ingest_result["status"] == "error":
        raise HTTPException(status_code=400, detail=ingest_result["message"])
        
    # 2. Add to repo
    source = await repo.add_source(
        notebook_id=data.notebook_id,
        title=data.title or ingest_result["metadata"].get("url", "New Source"),
        url=data.url,
        content=ingest_result["content"],
        source_type=ingest_result["source_type"],
        metadata=ingest_result["metadata"]
    )
    return source

@router.get("/notebooks/{notebook_id}/graph")
async def get_notebook_graph(notebook_id: str, repo: PostgresNotebookRepository = Depends(get_db)):
    return await repo.get_notebook_graph(notebook_id)
