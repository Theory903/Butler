import uuid
import structlog
from typing import Any, List, Optional
from sqlalchemy import select, delete, insert, update, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from domain.memory.notebook_models import (
    Notebook, Source, Note, SourceInsight, 
    SourceEmbedding, NotebookSources, NotebookNotes
)
from domain.contracts import INotebookRepository

logger = structlog.get_logger(__name__)

class PostgresNotebookRepository(INotebookRepository):
    """PostgreSQL implementation of the Notebook Repository using SQLAlchemy."""
    
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_notebook(self, account_id: str, name: str, description: str = "") -> Notebook:
        notebook = Notebook(
            account_id=uuid.UUID(account_id),
            name=name,
            description=description
        )
        self._db.add(notebook)
        await self._db.flush()
        return notebook

    async def get_notebooks(self, account_id: str, archived: bool = False) -> List[Notebook]:
        stmt = select(Notebook).where(
            Notebook.account_id == uuid.UUID(account_id),
            Notebook.archived == archived
        ).order_by(Notebook.updated_at.desc())
        
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_notebook(self, account_id: str, notebook_id: str) -> Optional[Notebook]:
        stmt = select(Notebook).where(
            Notebook.account_id == uuid.UUID(account_id),
            Notebook.id == uuid.UUID(notebook_id)
        ).options(
            selectinload(Notebook.sources),
            selectinload(Notebook.notes)
        )
        
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_source(self, notebook_id: str, title: str, source_type: str, asset: dict) -> Source:
        # 1. Look up notebook to get account_id
        notebook = await self._db.get(Notebook, uuid.UUID(notebook_id))
        if not notebook:
            raise ValueError(f"Notebook {notebook_id} not found")

        # 2. Create source
        source = Source(
            account_id=notebook.account_id,
            title=title,
            source_type=source_type,
            asset=asset
        )
        self._db.add(source)
        await self._db.flush()

        # 3. Link to notebook
        link = NotebookSources(notebook_id=notebook.id, source_id=source.id)
        self._db.add(link)
        await self._db.flush()
        
        return source

    async def get_sources(self, notebook_id: str) -> List[Source]:
        stmt = select(Source).join(NotebookSources).where(
            NotebookSources.notebook_id == uuid.UUID(notebook_id)
        ).order_by(Source.updated_at.desc())
        
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def add_note(self, notebook_id: str, title: str, content: str, note_type: str = "human") -> Note:
        notebook = await self._db.get(Notebook, uuid.UUID(notebook_id))
        if not notebook:
            raise ValueError(f"Notebook {notebook_id} not found")

        note = Note(
            account_id=notebook.account_id,
            title=title,
            content=content,
            note_type=note_type
        )
        self._db.add(note)
        await self._db.flush()

        link = NotebookNotes(notebook_id=notebook.id, note_id=note.id)
        self._db.add(link)
        await self._db.flush()
        
        return note

    async def get_notes(self, notebook_id: str) -> List[Note]:
        stmt = select(Note).join(NotebookNotes).where(
            NotebookNotes.notebook_id == uuid.UUID(notebook_id)
        ).order_by(Note.updated_at.desc())
        
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # ── Advanced Research Features ────────────────────────────────────────────

    async def get_shared_sources(self, source_id: str) -> List[Notebook]:
        """Find all notebooks that share a specific source."""
        stmt = select(Notebook).join(NotebookSources).where(
            NotebookSources.source_id == uuid.UUID(source_id)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def search_notebook_content(self, notebook_id: str, query_vector: List[float], limit: int = 10) -> List[Any]:
        """Hybrid search within a notebook using pgvector."""
        # This uses the 'source_embeddings' table linked to sources in this notebook
        stmt = select(Source, SourceEmbedding).join(SourceEmbedding).join(NotebookSources, Source.id == NotebookSources.source_id).where(
            NotebookSources.notebook_id == uuid.UUID(notebook_id)
        ).order_by(SourceEmbedding.embedding.cosine_distance(query_vector)).limit(limit)
        
        result = await self._db.execute(stmt)
        return list(result.all())

    async def get_graph_breadth(self, start_notebook_id: str, depth: int = 2) -> List[dict]:
        """Example recursive CTE for graph traversal within research relations."""
        # For Phase 12+: Navigate Notebook -> shared Sources -> other Notebooks
        sql = text("""
            WITH RECURSIVE research_graph AS (
                -- Anchor: start with the given notebook
                SELECT notebook_id, source_id, 1 as depth
                FROM notebook_sources
                WHERE notebook_id = :nb_id
                
                UNION ALL
                
                -- Recursive: find other notebooks sharing the SAME sources
                SELECT ns.notebook_id, ns.source_id, rg.depth + 1
                FROM notebook_sources ns
                JOIN research_graph rg ON ns.source_id = rg.source_id
                WHERE rg.depth < :max_depth
            )
            SELECT DISTINCT n.name, n.id 
            FROM research_graph rg
            JOIN notebooks n ON rg.notebook_id = n.id
            WHERE n.id != :nb_id
        """)
        
        result = await self._db.execute(sql, {"nb_id": uuid.UUID(start_notebook_id), "max_depth": depth})
        return [dict(row) for row in result]
