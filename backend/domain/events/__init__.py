"""Butler canonical event domain.

All events flowing through Butler must be represented as typed ButlerEvent
instances. Hermes runtime events are never consumed directly — they pass
through EventNormalizer first.

Governed by: docs/00-governance/transplant-constitution.md §7
"""

from domain.events.normalizer import EventNormalizer
from domain.events.schemas import (
    ApprovalDeniedEvent,
    ApprovalExpiredEvent,
    ApprovalGrantedEvent,
    ApprovalRequestedEvent,
    ButlerEvent,
    EventDeliveryClass,
    MemoryRetrievedEvent,
    MemoryStoredEvent,
    SessionEndedEvent,
    SessionStartedEvent,
    StreamApprovalRequiredEvent,
    StreamErrorEvent,
    StreamFinalEvent,
    # Stream events
    StreamStartEvent,
    StreamStatusEvent,
    StreamTokenEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    # Domain events
    TaskStartedEvent,
    TaskStepCompletedEvent,
    TaskStepStartedEvent,
    ToolExecutedEvent,
    ToolExecutingEvent,
    ToolFailedEvent,
)

__all__ = [
    "ButlerEvent",
    "EventDeliveryClass",
    "EventNormalizer",
    "StreamStartEvent",
    "StreamTokenEvent",
    "StreamToolCallEvent",
    "StreamToolResultEvent",
    "StreamApprovalRequiredEvent",
    "StreamStatusEvent",
    "StreamFinalEvent",
    "StreamErrorEvent",
    "TaskStartedEvent",
    "TaskStepStartedEvent",
    "TaskStepCompletedEvent",
    "TaskCompletedEvent",
    "TaskFailedEvent",
    "ToolExecutingEvent",
    "ToolExecutedEvent",
    "ToolFailedEvent",
    "MemoryStoredEvent",
    "MemoryRetrievedEvent",
    "ApprovalRequestedEvent",
    "ApprovalGrantedEvent",
    "ApprovalDeniedEvent",
    "ApprovalExpiredEvent",
    "SessionStartedEvent",
    "SessionEndedEvent",
]
