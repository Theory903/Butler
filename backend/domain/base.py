"""Domain base abstractions.

Every domain service contract and repository follows these base classes.
This enforces the boundary: domain must NOT import FastAPI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")
ID = TypeVar("ID")


class DomainService(ABC):
    """Marker base class for all domain service contracts.

    Domain services define WHAT can be done.
    Service implementations define HOW it is done.

    Rules:
    - MUST NOT import FastAPI, Starlette, or any HTTP concerns.
    - MUST NOT import from api/ layer.
    - MAY import from infrastructure/ via dependency injection.
    """


class Repository(ABC, Generic[T, ID]):
    """Base repository contract.

    Domain layer defines the interface.
    Infrastructure layer provides the SQLAlchemy implementation.
    """

    @abstractmethod
    async def get_by_id(self, id: ID) -> T | None:
        """Retrieve entity by primary key. Returns None if not found."""

    @abstractmethod
    async def save(self, entity: T) -> T:
        """Persist entity (insert or update). Returns saved entity."""

    @abstractmethod
    async def delete(self, id: ID) -> bool:
        """Delete entity by primary key. Returns True if deleted."""

    @abstractmethod
    async def exists(self, id: ID) -> bool:
        """Check existence without loading the full entity."""
