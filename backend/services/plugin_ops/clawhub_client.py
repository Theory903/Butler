"""ClawHub REST Client for remote plugin discovery and downloads.

Part of Phase 12A - Marketplace Connectivity.
"""

from __future__ import annotations

import httpx
import structlog
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from infrastructure.config import settings

logger = structlog.get_logger(__name__)


class ClawHubPackage(BaseModel):
    """Metadata for a package in the remote registry."""
    id: str = Field(..., alias="package_id")
    name: str
    publisher: str
    latest_version: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    risk_class: str = Field(..., alias="risk_tier")
    capabilities: List[str] = Field(default_factory=list)


class ClawHubClient:
    """
    Contract-driven REST client for ClawHub communication.
    
    Defaults to CLAW_HUB_URL. Mockable via environment for dev/test.
    """
    
    def __init__(self, base_url: Optional[str] = None, timeout: int = 10):
        self.base_url = base_url or settings.CLAW_HUB_URL
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"User-Agent": "Butler/0.1.0"},
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def search(
        self, 
        query: str, 
        tags: Optional[List[str]] = None, 
        capability: Optional[str] = None,
        risk_tier: Optional[int] = None
    ) -> List[ClawHubPackage]:
        """Search the remote registry for plugins/skills."""
        params = {"q": query}
        if tags:
            params["tags"] = ",".join(tags)
        if capability:
            params["capability"] = capability
        if risk_tier is not None:
            params["risk_tier"] = risk_tier

        try:
            response = await self.client.get("/v1/search", params=params)
            response.raise_for_status()
            data = response.json()
            return [ClawHubPackage(**p) for p in data.get("results", [])]
        except Exception as e:
            logger.error("clawhub_search_failed", error=str(e), query=query)
            return []

    async def get_package(self, package_id: str) -> Optional[ClawHubPackage]:
        """Get full metadata for a specific package."""
        try:
            response = await self.client.get(f"/v1/packages/{package_id}")
            response.raise_for_status()
            return ClawHubPackage(**response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
        except Exception as e:
            logger.error("clawhub_get_package_failed", error=str(e), package_id=package_id)
            raise

    async def get_versions(self, package_id: str) -> List[Dict[str, Any]]:
        """Get all available versions for a package."""
        try:
            response = await self.client.get(f"/v1/packages/{package_id}/versions")
            response.raise_for_status()
            return response.json().get("versions", [])
        except Exception as e:
            logger.error("clawhub_get_versions_failed", error=str(e), package_id=package_id)
            return []

    async def download_package(self, package_id: str, version: str) -> bytes:
        """Download the .zip / .tar.gz archive for a specific version."""
        try:
            response = await self.client.get(f"/v1/packages/{package_id}/versions/{version}/download")
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error("clawhub_download_failed", error=str(e), package_id=package_id, version=version)
            raise

    async def get_manifest(self, package_id: str, version: str) -> Dict[str, Any]:
        """Fetch just the openclaw.plugin.json manifest."""
        try:
            response = await self.client.get(f"/v1/packages/{package_id}/versions/{version}/manifest")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("clawhub_get_manifest_failed", error=str(e), package_id=package_id, version=version)
            raise

    async def get_signature(self, package_id: str, version: str) -> str:
        """Fetch the ED25519 signature for the package version."""
        try:
            response = await self.client.get(f"/v1/packages/{package_id}/versions/{version}/signature")
            response.raise_for_status()
            return response.json().get("signature", "")
        except Exception as e:
            logger.error("clawhub_get_signature_failed", error=str(e), package_id=package_id, version=version)
            raise
