from __future__ import annotations

from typing import Any
from uuid import UUID

from services.memory.twin_projection import DigitalTwinProjection
from services.memory.twin_repository_contracts import TwinProjectionRepository


class TwinProfileService:
    """High-level read service for Butler's materialized digital twin.

    Design goals:
    - never mutate the projection
    - return transport-safe dictionaries for API surfaces
    - expose a more product-shaped profile than the lower-level query service
    - gracefully handle missing snapshots
    """

    def __init__(self, repository: TwinProjectionRepository) -> None:
        self._repo = repository

    async def get_profile(self, user_id: UUID) -> dict[str, Any] | None:
        proj = await self._get_projection(user_id)
        if proj is None:
            return None

        return {
            "user_id": str(proj.user_id),
            "version": proj.version,
            "status": proj.status.value,
            "created_at": proj.created_at.isoformat(),
            "updated_at": proj.updated_at.isoformat(),
            "identity": proj.identity_profile.model_dump(mode="json"),
            "communication": proj.communication_profile.model_dump(mode="json"),
            "language": proj.language_profile.model_dump(mode="json"),
            "preferences": {
                "explicit": self._flatten_bucket(proj.preference_profile.explicit),
                "inferred": self._flatten_bucket(proj.preference_profile.inferred),
            },
            "dislikes": {
                "explicit": self._flatten_bucket(proj.dislike_profile.explicit),
                "inferred": self._flatten_bucket(proj.dislike_profile.inferred),
            },
            "constraints": {
                "hard": self._flatten_bucket(proj.constraint_profile.hard),
                "soft": self._flatten_bucket(proj.constraint_profile.soft),
            },
            "active_goals": [item.model_dump(mode="json") for item in proj.active_goals],
            "active_projects": [item.model_dump(mode="json") for item in proj.active_projects],
            "topics": [item.model_dump(mode="json") for item in proj.active_topics],
            "relationships": [item.model_dump(mode="json") for item in proj.active_relationships],
            "entities": [item.model_dump(mode="json") for item in proj.entities],
            "behavioral_signals": proj.behavioral_signals.model_dump(mode="json"),
            "multimodal": proj.multimodal_profile.model_dump(mode="json"),
            "consent": proj.consent_state.model_dump(mode="json"),
            "provenance": proj.provenance_summary.model_dump(mode="json"),
            "metadata": dict(proj.metadata),
        }

    async def get_projection_summary(self, user_id: UUID) -> dict[str, Any] | None:
        """Return a compact summary of the user's digital twin state."""
        proj = await self._get_projection(user_id)
        if proj is None:
            return None

        return {
            "user_id": str(proj.user_id),
            "version": proj.version,
            "status": proj.status.value,
            "primary_language": proj.language_profile.primary_language,
            "preferred_name": proj.identity_profile.preferred_name,
            "display_name": proj.identity_profile.display_name,
            "topic_count": len(proj.active_topics),
            "relationship_count": len(proj.active_relationships),
            "entity_count": len(proj.entities),
            "goal_count": len(proj.active_goals),
            "project_count": len(proj.active_projects),
            "events_processed": proj.provenance_summary.events_processed,
            "last_event_at": (
                proj.provenance_summary.last_event_at.isoformat()
                if proj.provenance_summary.last_event_at
                else None
            ),
            "updated_at": proj.updated_at.isoformat(),
        }

    async def get_identity(self, user_id: UUID) -> dict[str, Any] | None:
        proj = await self._get_projection(user_id)
        if proj is None:
            return None
        return proj.identity_profile.model_dump(mode="json")

    async def get_communication_style(self, user_id: UUID) -> dict[str, Any] | None:
        proj = await self._get_projection(user_id)
        if proj is None:
            return None
        return proj.communication_profile.model_dump(mode="json")

    async def get_language_preferences(self, user_id: UUID) -> dict[str, Any] | None:
        proj = await self._get_projection(user_id)
        if proj is None:
            return None
        return proj.language_profile.model_dump(mode="json")

    async def get_multimodal_profile(self, user_id: UUID) -> dict[str, Any] | None:
        proj = await self._get_projection(user_id)
        if proj is None:
            return None
        return proj.multimodal_profile.model_dump(mode="json")

    async def get_behavioral_signals(self, user_id: UUID) -> dict[str, Any] | None:
        proj = await self._get_projection(user_id)
        if proj is None:
            return None
        return proj.behavioral_signals.model_dump(mode="json")

    async def get_consent_summary(self, user_id: UUID) -> dict[str, Any] | None:
        proj = await self._get_projection(user_id)
        if proj is None:
            return None

        consent = proj.consent_state
        multimodal = proj.multimodal_profile

        return {
            "operational_memory": consent.operational_memory,
            "behavioral_memory": consent.behavioral_memory,
            "biometric_memory": consent.biometric_memory,
            "training_export": consent.training_export,
            "multimodal_consented": multimodal.consented,
            "voice_reference": multimodal.voice_reference,
            "face_reference": multimodal.face_reference,
            "multimodal_consent_at": (
                consent.multimodal_consent_at.isoformat() if consent.multimodal_consent_at else None
            ),
            "last_consent_at": (
                multimodal.last_consent_at.isoformat() if multimodal.last_consent_at else None
            ),
            "updated_at": consent.updated_at.isoformat(),
        }

    async def get_preferences(self, user_id: UUID) -> dict[str, Any]:
        proj = await self._get_projection(user_id)
        if proj is None:
            return {}
        return {
            "explicit": self._flatten_bucket(proj.preference_profile.explicit),
            "inferred": self._flatten_bucket(proj.preference_profile.inferred),
        }

    async def get_preference_by_key(
        self,
        user_id: UUID,
        key: str,
    ) -> dict[str, Any] | None:
        proj = await self._get_projection(user_id)
        if proj is None:
            return None

        normalized_key = key.strip()
        if not normalized_key:
            return None

        if normalized_key in proj.preference_profile.explicit:
            return self._normalize_record(
                key=normalized_key,
                bucket="explicit",
                record=proj.preference_profile.explicit[normalized_key],
            )

        if normalized_key in proj.preference_profile.inferred:
            return self._normalize_record(
                key=normalized_key,
                bucket="inferred",
                record=proj.preference_profile.inferred[normalized_key],
            )

        return None

    async def get_dislikes(self, user_id: UUID) -> dict[str, Any]:
        proj = await self._get_projection(user_id)
        if proj is None:
            return {}
        return {
            "explicit": self._flatten_bucket(proj.dislike_profile.explicit),
            "inferred": self._flatten_bucket(proj.dislike_profile.inferred),
        }

    async def has_profile(self, user_id: UUID) -> bool:
        proj = await self._get_projection(user_id)
        return proj is not None

    async def get_projection_version(self, user_id: UUID) -> int | None:
        proj = await self._get_projection(user_id)
        return proj.version if proj else None

    async def get_full_profile_raw(self, user_id: UUID) -> dict[str, Any] | None:
        """Return the raw, un-normalized projection payload."""
        proj = await self._get_projection(user_id)
        if proj is None:
            return None
        return proj.model_dump(mode="json")

    async def get_topics(self, user_id: UUID) -> list[dict[str, Any]]:
        proj = await self._get_projection(user_id)
        if proj is None:
            return []

        topics = sorted(
            proj.active_topics,
            key=lambda item: (
                -(item.strength or 0.0),
                item.name,
            ),
        )
        return [item.model_dump(mode="json") for item in topics]

    async def get_topic(self, user_id: UUID, topic_name: str) -> dict[str, Any] | None:
        proj = await self._get_projection(user_id)
        if proj is None:
            return None

        needle = topic_name.strip().lower()
        for topic in proj.active_topics:
            if topic.name.strip().lower() == needle:
                return topic.model_dump(mode="json")
        return None

    async def get_relationships(self, user_id: UUID) -> list[dict[str, Any]]:
        proj = await self._get_projection(user_id)
        if proj is None:
            return []

        relationships = sorted(
            proj.active_relationships,
            key=lambda item: (
                -(item.strength or 0.0),
                item.label,
                item.entity_id,
            ),
        )
        return [item.model_dump(mode="json") for item in relationships]

    async def get_entities(self, user_id: UUID) -> list[dict[str, Any]]:
        proj = await self._get_projection(user_id)
        if proj is None:
            return []

        entities = sorted(
            proj.entities,
            key=lambda item: (
                item.kind,
                item.name.lower(),
                item.id,
            ),
        )
        return [item.model_dump(mode="json") for item in entities]

    async def get_entity(self, user_id: UUID, entity_id: str) -> dict[str, Any] | None:
        proj = await self._get_projection(user_id)
        if proj is None:
            return None

        for entity in proj.entities:
            if entity.id == entity_id:
                return entity.model_dump(mode="json")
        return None

    async def find_entities(
        self,
        user_id: UUID,
        query: str,
    ) -> list[dict[str, Any]]:
        proj = await self._get_projection(user_id)
        if proj is None:
            return []

        needle = query.strip().lower()
        if not needle:
            return []

        matches = []
        for entity in proj.entities:
            if needle in entity.name.lower():
                matches.append(entity)
                continue
            if any(needle in alias.lower() for alias in entity.aliases):
                matches.append(entity)

        matches.sort(key=lambda item: (item.kind, item.name.lower(), item.id))
        return [item.model_dump(mode="json") for item in matches]

    async def get_active_goals(self, user_id: UUID) -> list[dict[str, Any]]:
        proj = await self._get_projection(user_id)
        if proj is None:
            return []

        goals = sorted(
            proj.active_goals,
            key=lambda item: (
                item.status != "active",
                -item.priority,
                item.title.lower(),
                item.id,
            ),
        )
        return [item.model_dump(mode="json") for item in goals]

    async def get_active_projects(self, user_id: UUID) -> list[dict[str, Any]]:
        proj = await self._get_projection(user_id)
        if proj is None:
            return []

        projects = sorted(
            proj.active_projects,
            key=lambda item: (
                item.status != "active",
                -(item.importance or 0.0),
                -(item.recency or 0.0),
                item.name.lower(),
                item.id,
            ),
        )
        return [item.model_dump(mode="json") for item in projects]

    async def get_constraints(self, user_id: UUID) -> dict[str, Any]:
        proj = await self._get_projection(user_id)
        if proj is None:
            return {"hard": {}, "soft": {}}
        return {
            "hard": self._flatten_bucket(proj.constraint_profile.hard),
            "soft": self._flatten_bucket(proj.constraint_profile.soft),
        }

    async def _get_projection(self, user_id: UUID) -> DigitalTwinProjection | None:
        snapshot = await self._repo.get_snapshot(user_id)
        return snapshot.projection if snapshot else None

    def _flatten_bucket(self, bucket: dict[str, Any]) -> dict[str, Any]:
        """Return a bucket where records are flattened to just their 'value' field."""
        flattened: dict[str, Any] = {}
        for key, value in bucket.items():
            if isinstance(value, dict) and "value" in value:
                flattened[key] = value["value"]
            else:
                flattened[key] = value
        return flattened

    def _normalize_record(
        self,
        *,
        key: str,
        bucket: str,
        record: Any,
    ) -> dict[str, Any]:
        """Normalize a raw record into a standard API response shape."""
        if isinstance(record, dict):
            return {
                "key": key,
                "bucket": bucket,
                "value": record.get("value"),
                "confidence": record.get("confidence"),
                "source": record.get("source"),
                "domain": record.get("domain"),
                "reason": record.get("reason"),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                "redacted": bool(record.get("redacted", False)),
            }

        return {
            "key": key,
            "bucket": bucket,
            "value": record,
            "confidence": None,
            "source": None,
            "domain": None,
            "reason": None,
            "created_at": None,
            "updated_at": None,
            "redacted": False,
        }
