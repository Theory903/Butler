from __future__ import annotations

from uuid import uuid4

from services.memory.twin_events import (
    ConfidenceLevel,
    EventFactory,
)
from services.memory.twin_projection import (
    ProjectionStatus,
    apply_event_to_projection,
    new_projection,
)


class TestTwinProjection:
    """Test digital twin projection reducer."""

    def test_new_projection_creation(self):
        """Test creating an empty projection."""
        user_id = uuid4()
        projection = new_projection(user_id)

        assert projection.user_id == user_id
        assert projection.version == 0
        assert projection.status == ProjectionStatus.ACTIVE
        assert projection.active_goals == []
        assert projection.active_projects == []
        assert projection.active_relationships == []
        assert projection.active_topics == []
        assert projection.preference_profile.explicit == {}
        assert projection.preference_profile.inferred == {}

    def test_apply_conversation_turn_event(self):
        """Test applying a conversation turn event."""
        user_id = uuid4()
        projection = new_projection(user_id)

        event = EventFactory.conversation_turn_recorded(
            user_id=user_id,
            session_id="session_123",
            role="user",
            content="I prefer Python for coding",
            turn_index=1,
        )

        updated_projection = apply_event_to_projection(projection, event)

        assert updated_projection.version == 1
        assert updated_projection.user_id == user_id

    def test_apply_preference_updated_event(self):
        """Test applying a preference update event."""
        user_id = uuid4()
        projection = new_projection(user_id)

        event = EventFactory.preference_updated(
            user_id=user_id,
            key="language",
            value="python",
            domain="coding",
            explicit=True,
            confidence_score=0.95,
        )

        updated_projection = apply_event_to_projection(projection, event)

        assert updated_projection.version == 1
        assert "language" in updated_projection.preference_profile.explicit
        assert updated_projection.preference_profile.explicit["language"]["value"] == "python"
        assert (
            updated_projection.preference_profile.explicit["language"]["confidence"]
            == ConfidenceLevel.EXPLICIT
        )
        assert updated_projection.preference_profile.explicit["language"]["source"] == "explicit"

    def test_projection_idempotency(self):
        user_id = uuid4()
        projection = new_projection(user_id)

        event = EventFactory.preference_updated(
            user_id=user_id,
            key="coffee",
            value="black",
            domain="beverage",
            explicit=True,
            confidence_score=0.9,
        )

        first_update = apply_event_to_projection(projection, event)
        second_update = apply_event_to_projection(first_update, event)

        assert first_update.version == 1
        assert second_update.version == 2

    def test_projection_state_isolation(self):
        """Test that projection updates don't mutate original state."""
        user_id = uuid4()
        original = new_projection(user_id)

        event = EventFactory.preference_updated(
            user_id=user_id,
            key="music",
            value="jazz",
            domain="entertainment",
            explicit=True,
            confidence_score=0.8,
        )

        updated = apply_event_to_projection(original, event)

        assert original.version == 0
        assert "music" not in original.preference_profile.explicit
        assert updated.version == 1
        assert updated.preference_profile.explicit["music"]["value"] == "jazz"

    def test_forgotten_projection_status(self):
        """Test forgotten projection status handling."""
        user_id = uuid4()
        projection = new_projection(user_id)
        assert projection.status == ProjectionStatus.ACTIVE

    def test_projection_with_multiple_events(self):
        """Test applying multiple events in sequence."""
        user_id = uuid4()
        projection = new_projection(user_id)

        events = [
            EventFactory.preference_updated(
                user_id=user_id,
                key="language",
                value="python",
                domain="coding",
                explicit=True,
                confidence_score=0.9,
            ),
            EventFactory.preference_updated(
                user_id=user_id,
                key="ide",
                value="vscode",
                domain="tools",
                explicit=True,
                confidence_score=0.85,
            ),
        ]

        after_first = apply_event_to_projection(projection, events[0])
        assert after_first.version == 1
        assert after_first.preference_profile.explicit["language"]["value"] == "python"

        after_second = apply_event_to_projection(after_first, events[1])
        assert after_second.version == 2
        assert after_second.preference_profile.explicit["language"]["value"] == "python"
        assert after_second.preference_profile.explicit["ide"]["value"] == "vscode"
