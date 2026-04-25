import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.deps import get_db

router = APIRouter(prefix="/research", tags=["research"])


async def get_notebook_repo(db=Depends(get_db)) -> Any:
    from services.memory.notebook_repo import PostgresNotebookRepository

    return PostgresNotebookRepository(db)


async def get_transformation_service() -> Any:
    from services.memory.transformation_service import TransformationService

    return TransformationService()


class NotebookCreate(BaseModel):
    title: str
    description: str | None = None


class SourceCreate(BaseModel):
    notebook_id: str
    url: str
    title: str | None = None


@router.post("/notebooks")
async def create_notebook(data: NotebookCreate, repo: Any = Depends(get_notebook_repo)):
    # Mocking account_id for now as is consistent with other routes
    account_id = str(uuid.uuid4())
    return await repo.create_notebook(
        account_id=account_id, title=data.title, description=data.description
    )


@router.get("/notebooks")
async def list_notebooks(repo: Any = Depends(get_notebook_repo)):
    account_id = str(uuid.uuid4())
    return await repo.list_notebooks(account_id)


@router.post("/sources")
async def add_source(
    data: SourceCreate,
    repo: Any = Depends(get_notebook_repo),
    transformer: Any = Depends(get_transformation_service),
):
    # 1. Ingest content based on URL
    if "youtube.com" in data.url or "youtu.be" in data.url:
        ingest_result = await transformer.ingest_youtube(data.url)
    else:
        ingest_result = await transformer.ingest_url(data.url)

    if ingest_result["status"] == "error":
        raise HTTPException(status_code=400, detail=ingest_result["message"])

    # 2. Add to repo
    return await repo.add_source(
        notebook_id=data.notebook_id,
        title=data.title or ingest_result["metadata"].get("url", "New Source"),
        url=data.url,
        content=ingest_result["content"],
        source_type=ingest_result["source_type"],
        metadata=ingest_result["metadata"],
    )


@router.get("/notebooks/{notebook_id}/graph")
async def get_notebook_graph(notebook_id: str, repo: Any = Depends(get_notebook_repo)):
    return await repo.get_notebook_graph(notebook_id)
