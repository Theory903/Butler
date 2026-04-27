import logging
from typing import Optional

from neo4j import AsyncDriver, AsyncGraphDatabase

from infrastructure.config import settings

import structlog

logger = structlog.get_logger(__name__)


class Neo4jClient:
    """Butler's Neo4j Graph Database Client (Oracle-Grade)."""

    _instance: Optional["Neo4jClient"] = None
    _driver: AsyncDriver | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def connect(self):
        """Establish connection to the Neo4j cluster."""
        if self._driver is None:
            try:
                self._driver = AsyncGraphDatabase.driver(
                    settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
                )
                await self._driver.verify_connectivity()
                logger.info("Neo4j connection established successfully.")
            except Exception as e:
                logger.error(f"Failed to connect to Neo4j: {e}")
                raise

    async def close(self):
        """Close the Neo4j driver connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed.")

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4jClient is not connected. Call connect() first.")
        return self._driver

    async def execute_query(self, query: str, parameters: dict | None = None):
        """Helper to run a Cypher query in a single transaction."""
        if not self._driver:
            await self.connect()

        async with self._driver.session() as session:
            result = await session.run(query, parameters or {})
            return await result.data()


# Global instance
neo4j_client = Neo4jClient()
