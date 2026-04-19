"""Butler canonical event domain.

All events flowing through Butler must be represented as typed ButlerEvent
instances. Hermes runtime events are never consumed directly — they pass
through EventNormalizer first.

Governed by: docs/00-governance/transplant-constitution.md §7
"""

from domain.events.schemas import (
    ButlerEvent,
    EventDeliveryClass,
    # Stream events
    StreamStartEvent,
    StreamTokenEvent,
    StreamToolCallEvent,
    StreamToolResultEvent,
    StreamApprovalRequiredEvent,
    StreamStatusEvent,
    StreamFinalEvent,
    StreamErrorEvent,
    # Domain events
    TaskStartedEvent,
    TaskStepStartedEvent,
    TaskStepCompletedEvent,
    TaskCompletedEvent,
    TaskFailedEvent,
    ToolExecutingEvent,
    ToolExecutedEvent,
    ToolFailedEvent,
    MemoryStoredEvent,
    MemoryRetrievedEvent,
    ApprovalRequestedEvent,
    ApprovalGrantedEvent,
    ApprovalDeniedEvent,
    ApprovalExpiredEvent,
    SessionStartedEvent,
    SessionEndedEvent,
)
from domain.events.normalizer import EventNormalizer

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
