"""Butler Skill Marketplace.

Phase E.3: Skill marketplace for discovering and managing skills.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SkillListing:
    """A skill listing in the marketplace."""

    skill_id: str
    name: str
    description: str
    category: str
    version: str
    author: str
    downloads: int = 0
    rating: float = 0.0
    is_installed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class ButlerSkillMarketplace:
    """Marketplace for Butler skills.

    This marketplace:
    - Lists available skills
    - Tracks skill ratings and downloads
    - Provides skill search and discovery
    - Manages skill installation status
    """

    def __init__(self):
        """Initialize the skill marketplace."""
        self._listings: dict[str, SkillListing] = {}
        self._categories: dict[str, set[str]] = {}

    def add_listing(self, listing: SkillListing) -> None:
        """Add a skill listing.

        Args:
            listing: Skill listing to add
        """
        self._listings[listing.skill_id] = listing

        category = listing.category
        if category not in self._categories:
            self._categories[category] = set()
        self._categories[category].add(listing.skill_id)

        logger.info("skill_listing_added", skill_id=listing.skill_id)

    def remove_listing(self, skill_id: str) -> None:
        """Remove a skill listing.

        Args:
            skill_id: Skill identifier
        """
        if skill_id in self._listings:
            listing = self._listings[skill_id]
            category = listing.category

            del self._listings[skill_id]

            if category in self._categories and skill_id in self._categories[category]:
                self._categories[category].remove(skill_id)

            logger.info("skill_listing_removed", skill_id=skill_id)

    def get_listing(self, skill_id: str) -> SkillListing | None:
        """Get a skill listing.

        Args:
            skill_id: Skill identifier

        Returns:
            Skill listing or None
        """
        return self._listings.get(skill_id)

    def list_listings(self, category: str | None = None) -> list[SkillListing]:
        """List skill listings, optionally filtered by category.

        Args:
            category: Optional category filter

        Returns:
            List of skill listings
        """
        if category:
            skill_ids = self._categories.get(category, set())
            return [self._listings[sid] for sid in skill_ids if sid in self._listings]
        return list(self._listings.values())

    def search(self, query: str) -> list[SkillListing]:
        """Search skill listings.

        Args:
            query: Search query

        Returns:
            List of matching listings
        """
        query_lower = query.lower()
        matches = []

        for listing in self._listings.values():
            name = listing.name.lower()
            description = listing.description.lower()

            if query_lower in name or query_lower in description:
                matches.append(listing)

        return matches

    def mark_installed(self, skill_id: str) -> None:
        """Mark a skill as installed.

        Args:
            skill_id: Skill identifier
        """
        if skill_id in self._listings:
            self._listings[skill_id].is_installed = True
            logger.info("skill_marked_installed", skill_id=skill_id)

    def increment_downloads(self, skill_id: str) -> None:
        """Increment download count for a skill.

        Args:
            skill_id: Skill identifier
        """
        if skill_id in self._listings:
            self._listings[skill_id].downloads += 1

    def get_popular(self, limit: int = 10) -> list[SkillListing]:
        """Get popular skills by downloads.

        Args:
            limit: Maximum number to return

        Returns:
            List of popular skills
        """
        sorted_listings = sorted(
            self._listings.values(),
            key=lambda x: x.downloads,
            reverse=True,
        )
        return sorted_listings[:limit]

    def get_top_rated(self, limit: int = 10) -> list[SkillListing]:
        """Get top-rated skills.

        Args:
            limit: Maximum number to return

        Returns:
            List of top-rated skills
        """
        sorted_listings = sorted(
            self._listings.values(),
            key=lambda x: x.rating,
            reverse=True,
        )
        return sorted_listings[:limit]
