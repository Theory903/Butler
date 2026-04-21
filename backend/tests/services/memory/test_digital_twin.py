"""
Tests for Digital Twin Memory System.

Tests:
- Layer isolation
- Consent enforcement
- Retention policies
- Entity resolution
- Temporal reasoning
"""

import datetime
import uuid
from uuid import UUID

import pytest

from services.memory.digital_twin import (
    DigitalTwinProfile,
    TwinBuilder,
    TwinQueryEngine,
    TrainingDataTransformer,
    EntityResolver,
    TemporalReasoner,
    ConsentTier,
    MemoryLayerType,
    EntityType,
    EpisodicMemory,
    MemoryFact,
    Preference,
    EntityNode,
    RelationshipEdge,
    FileMemory,
)


@pytest.fixture
def test_user_id() -> UUID:
    return uuid.uuid4()


@pytest.fixture
def empty_profile(test_user_id: UUID) -> DigitalTwinProfile:
    return DigitalTwinProfile(user_id=test_user_id)


class TestDigitalTwinProfile:
    def test_profile_creation(self, test_user_id: UUID) -> None:
        profile = DigitalTwinProfile(user_id=test_user_id)
        assert profile.user_id == test_user_id
        assert profile.consent_tier == ConsentTier.NEVER_TRAIN
        assert all(layer.entry_count == 0 for layer in (
            profile.episodic, profile.semantic, profile.preferences,
            profile.graph, profile.files, profile.training
        ))


class TestTwinBuilder:
    def test_add_interaction(self, test_user_id: UUID) -> None:
        builder = TwinBuilder(test_user_id)
        interaction = EpisodicMemory(
            interaction_type="chat",
            content="Hello Butler",
            importance=0.7
        )
        builder.add_interaction(interaction)
        profile = builder.build()

        assert profile.episodic.entry_count == 1
        assert len(profile.episodic.episodes) == 1
        assert profile.episodic.episodes[0].content == "Hello Butler"

    def test_add_fact(self, test_user_id: UUID) -> None:
        builder = TwinBuilder(test_user_id)
        fact = MemoryFact(
            entity_id=uuid.uuid4(),
            attribute="name",
            value="Alice",
            confidence=0.95
        )
        builder.add_fact(fact)
        profile = builder.build()

        assert profile.semantic.entry_count == 1
        assert fact.fact_id in profile.semantic.facts

    def test_add_preference(self, test_user_id: UUID) -> None:
        builder = TwinBuilder(test_user_id)
        pref = Preference(
            domain="ui",
            key="theme",
            value="dark",
            strength=0.9
        )
        builder.add_preference(pref)
        profile = builder.build()

        assert profile.preferences.entry_count == 1
        assert "ui:theme" in profile.preferences.preferences

    def test_add_entity_and_relationship(self, test_user_id: UUID) -> None:
        builder = TwinBuilder(test_user_id)
        entity = EntityNode(
            entity_type=EntityType.PERSON,
            canonical_name="Bob"
        )
        builder.add_entity(entity)

        edge = RelationshipEdge(
            from_entity=entity.entity_id,
            to_entity=uuid.uuid4(),
            relationship_type="friend_of"
        )
        builder.add_relationship(edge)
        profile = builder.build()

        assert profile.graph.entry_count == 2
        assert entity.entity_id in profile.graph.entities
        assert edge.edge_id in profile.graph.edges


class TestTwinQueryEngine:
    def test_get_recent_episodes(self, empty_profile: DigitalTwinProfile) -> None:
        # Add test episodes
        for i in range(15):
            empty_profile.episodic.episodes.append(EpisodicMemory(
                interaction_type="chat",
                content=f"Message {i}",
                timestamp=datetime.datetime.utcnow() - datetime.timedelta(hours=i)
            ))
        empty_profile.episodic.entry_count = 15

        engine = TwinQueryEngine(empty_profile)
        recent = engine.get_recent_episodes(limit=5)

        assert len(recent) == 5
        assert recent[0].content == "Message 0"
        assert recent[4].content == "Message 4"

    def test_get_preference(self, empty_profile: DigitalTwinProfile) -> None:
        pref = Preference(domain="ui", key="theme", value="dark", strength=0.9)
        empty_profile.preferences.preferences["ui:theme"] = pref
        engine = TwinQueryEngine(empty_profile)

        assert engine.get_preference("ui", "theme") == "dark"
        assert engine.get_preference("ui", "not_found", default="light") == "light"

    def test_find_entities(self, empty_profile: DigitalTwinProfile) -> None:
        entity = EntityNode(entity_type=EntityType.PERSON, canonical_name="Alice Smith")
        entity.aliases.add("Ally")
        empty_profile.graph.entities[entity.entity_id] = entity
        engine = TwinQueryEngine(empty_profile)

        matches = engine.find_entities("alice")
        assert len(matches) == 1
        assert matches[0].canonical_name == "Alice Smith"

        matches = engine.find_entities("ally")
        assert len(matches) == 1


class TestTrainingDataTransformer:
    def test_create_sample_never_train(self, empty_profile: DigitalTwinProfile) -> None:
        empty_profile.consent_tier = ConsentTier.NEVER_TRAIN
        sample = TrainingDataTransformer.create_sample(empty_profile, "input", "output")
        assert sample is None
        assert empty_profile.training.entry_count == 0

    def test_create_sample_private_eval(self, empty_profile: DigitalTwinProfile) -> None:
        empty_profile.consent_tier = ConsentTier.PRIVATE_EVAL_ONLY
        sample = TrainingDataTransformer.create_sample(empty_profile, "input", "output")
        assert sample is None
        assert empty_profile.training.entry_count == 0

    def test_create_sample_opt_in(self, empty_profile: DigitalTwinProfile) -> None:
        empty_profile.consent_tier = ConsentTier.OPT_IN
        sample = TrainingDataTransformer.create_sample(empty_profile, "input", "output")
        assert sample is not None
        assert sample.anonymized is True
        assert empty_profile.training.entry_count == 1

    def test_consent_checks(self, empty_profile: DigitalTwinProfile) -> None:
        empty_profile.consent_tier = ConsentTier.NEVER_TRAIN
        assert not TrainingDataTransformer.can_use_for_training(empty_profile)
        assert not TrainingDataTransformer.can_use_for_evaluation(empty_profile)

        empty_profile.consent_tier = ConsentTier.PRIVATE_EVAL_ONLY
        assert not TrainingDataTransformer.can_use_for_training(empty_profile)
        assert TrainingDataTransformer.can_use_for_evaluation(empty_profile)

        empty_profile.consent_tier = ConsentTier.OPT_IN
        assert TrainingDataTransformer.can_use_for_training(empty_profile)
        assert TrainingDataTransformer.can_use_for_evaluation(empty_profile)


class TestEntityResolver:
    def test_resolve_new_entity(self, empty_profile: DigitalTwinProfile) -> None:
        resolver = EntityResolver(empty_profile)
        entity = resolver.resolve("Alice", EntityType.PERSON)

        assert entity.canonical_name == "Alice"
        assert entity.entity_type == EntityType.PERSON
        assert entity.entity_id in empty_profile.graph.entities
        assert empty_profile.graph.entry_count == 1

    def test_resolve_existing_entity(self, empty_profile: DigitalTwinProfile) -> None:
        existing = EntityNode(entity_type=EntityType.PERSON, canonical_name="Alice Smith")
        existing.aliases.add("Alice")
        empty_profile.graph.entities[existing.entity_id] = existing
        empty_profile.graph.entry_count = 1

        resolver = EntityResolver(empty_profile)
        resolved = resolver.resolve("Alice", EntityType.PERSON)

        assert resolved.entity_id == existing.entity_id
        assert empty_profile.graph.entry_count == 1  # No new entity created

    def test_add_alias(self, empty_profile: DigitalTwinProfile) -> None:
        entity = EntityNode(entity_type=EntityType.PERSON, canonical_name="Alice")
        empty_profile.graph.entities[entity.entity_id] = entity

        resolver = EntityResolver(empty_profile)
        resolver.add_alias(entity.entity_id, "Ally")

        assert "Ally" in empty_profile.graph.entities[entity.entity_id].aliases


class TestTemporalReasoner:
    def test_get_fact_at_time(self, empty_profile: DigitalTwinProfile) -> None:
        entity_id = uuid.uuid4()
        now = datetime.datetime.utcnow()

        # Old fact
        old_fact = MemoryFact(
            entity_id=entity_id,
            attribute="location",
            value="New York",
            first_observed=now - datetime.timedelta(days=30),
            last_observed=now - datetime.timedelta(days=10)
        )
        # New fact
        new_fact = MemoryFact(
            entity_id=entity_id,
            attribute="location",
            value="London",
            first_observed=now - datetime.timedelta(days=5),
            last_observed=now
        )

        empty_profile.semantic.facts[old_fact.fact_id] = old_fact
        empty_profile.semantic.facts[new_fact.fact_id] = new_fact

        reasoner = TemporalReasoner(empty_profile)

        # Check at 15 days ago - should get old fact
        fact_15d = reasoner.get_fact_at_time(entity_id, "location", now - datetime.timedelta(days=15))
        assert fact_15d is not None
        assert fact_15d.value == "New York"

        # Check now - should get new fact
        fact_now = reasoner.get_fact_at_time(entity_id, "location", now)
        assert fact_now is not None
        assert fact_now.value == "London"
