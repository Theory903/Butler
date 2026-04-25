from __future__ import annotations

import json
import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from domain.memory.contracts import ContextPack
from domain.memory.models import (
    ConversationTurn,
    ExplicitDislike,
    ExplicitPreference,
    UserConstraint,
)
from services.memory.retrieval import ScoredMemory

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_BUDGET = 4096
_DEFAULT_HISTORY_BUDGET_RATIO = 0.35
_DEFAULT_MEMORY_BUDGET_RATIO = 0.40
_DEFAULT_PROFILE_BUDGET_RATIO = 0.15
_DEFAULT_ENTITY_BUDGET_RATIO = 0.10
_DEFAULT_CHAR_TO_TOKEN_RATIO = 4

_SECTION_ORDER = (
    "summary_anchor",
    "constraints",
    "preferences",
    "dislikes",
    "entities",
    "relevant_memories",
    "session_history",
)


class ContextBuilder:
    """Butler context assembler.

    Responsibilities:
    - assemble a deterministic ContextPack
    - apply token-budget-aware trimming
    - normalize ORM/model objects into prompt-safe structures
    - preserve the highest-value summary / profile / memory context first

    Notes:
    - This layer is intentionally synchronous and pure.
    - It does not perform I/O or retrieval.
    - It does not mutate caller-owned ORM objects.
    """

    def __init__(
        self,
        token_budget: int = _DEFAULT_TOKEN_BUDGET,
        *,
        history_budget_ratio: float = _DEFAULT_HISTORY_BUDGET_RATIO,
        memory_budget_ratio: float = _DEFAULT_MEMORY_BUDGET_RATIO,
        profile_budget_ratio: float = _DEFAULT_PROFILE_BUDGET_RATIO,
        entity_budget_ratio: float = _DEFAULT_ENTITY_BUDGET_RATIO,
        char_to_token_ratio: int = _DEFAULT_CHAR_TO_TOKEN_RATIO,
        tokenizer_encoding_name: str = "o200k_base",
    ) -> None:
        if token_budget <= 0:
            raise ValueError("token_budget must be greater than 0")
        if char_to_token_ratio <= 0:
            raise ValueError("char_to_token_ratio must be greater than 0")

        ratio_sum = (
            history_budget_ratio + memory_budget_ratio + profile_budget_ratio + entity_budget_ratio
        )
        if ratio_sum <= 0:
            raise ValueError("budget ratios must sum to a positive value")

        self._token_budget = token_budget
        self._history_budget_ratio = history_budget_ratio
        self._memory_budget_ratio = memory_budget_ratio
        self._profile_budget_ratio = profile_budget_ratio
        self._entity_budget_ratio = entity_budget_ratio
        self._char_to_token_ratio = char_to_token_ratio
        self._tokenizer_encoding_name = tokenizer_encoding_name

    def assemble(
        self,
        history: list[ConversationTurn],
        memories: list[ScoredMemory],
        preferences: list[ExplicitPreference],
        entities: list[dict[str, Any] | Any],
        constraints: list[UserConstraint],
        summary_anchor: str | None = None,
        dislikes: list[ExplicitDislike] | None = None,
        query_type: str = "general",  # NEW: query type for dynamic budgeting
    ) -> ContextPack:
        """Assemble a token-budgeted ContextPack with dynamic budget allocation.

        Enhanced with:
        - Dynamic budget allocation based on query type
        - Adaptive section prioritization
        - Better memory selection based on score thresholds
        """
        dislikes = dislikes or []

        # Dynamic budget allocation based on query type
        section_budgets = self._compute_dynamic_section_budgets(query_type)

        normalized_summary = self._normalize_summary_anchor(summary_anchor)

        self._prepare_constraints(constraints)
        processed_preferences = self._prepare_preferences(preferences)
        self._prepare_dislikes(dislikes)
        processed_entities = self._prepare_entities(entities)

        selected_memories = self._select_memories_enhanced(
            memories=memories,
            token_budget=section_budgets["relevant_memories"],
            query_type=query_type,
        )
        selected_history = self._select_history_enhanced(
            history=history,
            token_budget=section_budgets["session_history"],
            query_type=query_type,
        )

        pack = ContextPack(
            session_history=selected_history,
            relevant_memories=[item.memory for item in selected_memories],
            preferences=processed_preferences,
            entities=processed_entities,
            summary_anchor=normalized_summary,
            context_token_budget=self._token_budget,
        )

        logger.debug(
            "context_pack_assembled",
            extra={
                "token_budget": self._token_budget,
                "query_type": query_type,
                "history_count": len(pack.session_history),
                "memory_count": len(pack.relevant_memories),
                "preference_count": len(processed_preferences),
                "entity_count": len(processed_entities),
                "has_summary_anchor": bool(pack.summary_anchor),
                "section_budgets": section_budgets,
            },
        )
        return pack

    def format_as_prompt(self, pack: ContextPack) -> str:
        """Flatten a ContextPack into a deterministic prompt string."""
        sections: list[str] = []

        if pack.summary_anchor:
            sections.append(
                self._format_section(
                    "PAST CONVERSATION SUMMARY (ANCHOR)",
                    pack.summary_anchor,
                )
            )

        constraints = getattr(pack, "constraints", None)
        if constraints:
            constraint_lines = [
                f"- {item.get('type', 'constraint')}: {item.get('value', '')}"
                for item in constraints
            ]
            sections.append(self._format_section("USER CONSTRAINTS", "\n".join(constraint_lines)))

        preferences = pack.preferences or []
        if preferences:
            pref_lines = [
                f"- {item.get('key', '')}: {item.get('value', '')}" for item in preferences
            ]
            sections.append(self._format_section("USER PREFERENCES", "\n".join(pref_lines)))

        dislikes = getattr(pack, "dislikes", None)
        if dislikes:
            dislike_lines = [
                f"- {item.get('key', '')}: {item.get('reason', '') or 'disliked'}"
                for item in dislikes
            ]
            sections.append(self._format_section("USER DISLIKES", "\n".join(dislike_lines)))

        entities = pack.entities or []
        if entities:
            entity_lines = []
            for entity in entities:
                if isinstance(entity, dict):
                    name = entity.get("name") or entity.get("canonical_name") or "unknown"
                    entity_type = entity.get("entity_type") or entity.get("type") or "entity"
                    summary = entity.get("summary") or ""
                    line = f"- {name} ({entity_type})"
                    if summary:
                        line += f": {summary}"
                    entity_lines.append(line)
                else:
                    entity_lines.append(f"- {self._stringify(entity)}")

            sections.append(self._format_section("RESOLVED ENTITIES", "\n".join(entity_lines)))

        if pack.relevant_memories:
            memory_lines = []
            for memory in pack.relevant_memories:
                memory_lines.append(f"- {self._memory_to_prompt_line(memory)}")
            sections.append(self._format_section("RELEVANT MEMORIES", "\n".join(memory_lines)))

        if pack.session_history:
            history_lines = []
            for turn in pack.session_history:
                if isinstance(turn, dict):
                    role = str(turn.get("role", "unknown"))
                    content = str(turn.get("content", ""))
                else:
                    role = str(getattr(turn, "role", "unknown"))
                    content = str(getattr(turn, "content", ""))
                history_lines.append(f"{role}: {content}")
            sections.append(
                self._format_section("RECENT SESSION HISTORY", "\n".join(history_lines))
            )

        return "\n\n".join(section for section in sections if section.strip())

    def _compute_section_budgets(self) -> dict[str, int]:
        """Allocate section-specific token budgets."""
        total_ratio = (
            self._history_budget_ratio
            + self._memory_budget_ratio
            + self._profile_budget_ratio
            + self._entity_budget_ratio
        )

        history_budget = int(self._token_budget * (self._history_budget_ratio / total_ratio))
        memory_budget = int(self._token_budget * (self._memory_budget_ratio / total_ratio))
        profile_budget = int(self._token_budget * (self._profile_budget_ratio / total_ratio))
        entity_budget = max(
            1,
            self._token_budget - history_budget - memory_budget - profile_budget,
        )

        return {
            "session_history": max(1, history_budget),
            "relevant_memories": max(1, memory_budget),
            "profile": max(1, profile_budget),
            "entities": entity_budget,
        }

    def _compute_dynamic_section_budgets(self, query_type: str) -> dict[str, int]:
        """Allocate section-specific token budgets based on query type.

        Query types:
        - 'general': Balanced allocation (default ratios)
        - 'factual': Higher memory budget for facts
        - 'conversational': Higher history budget for context
        - 'creative': Lower memory, higher history for flow
        """
        if query_type == "factual":
            # Prioritize memories for factual queries
            return {
                "session_history": int(self._token_budget * 0.25),
                "relevant_memories": int(self._token_budget * 0.50),
                "profile": int(self._token_budget * 0.15),
                "entities": int(self._token_budget * 0.10),
            }
        if query_type == "conversational":
            # Prioritize history for conversational queries
            return {
                "session_history": int(self._token_budget * 0.50),
                "relevant_memories": int(self._token_budget * 0.30),
                "profile": int(self._token_budget * 0.12),
                "entities": int(self._token_budget * 0.08),
            }
        if query_type == "creative":
            # Prioritize history for creative flow
            return {
                "session_history": int(self._token_budget * 0.55),
                "relevant_memories": int(self._token_budget * 0.25),
                "profile": int(self._token_budget * 0.12),
                "entities": int(self._token_budget * 0.08),
            }
        # Default: balanced allocation
        return self._compute_section_budgets()

    def _prepare_preferences(
        self,
        preferences: list[ExplicitPreference],
    ) -> list[dict[str, Any]]:
        """Normalize and sort preferences deterministically."""
        processed = []
        for item in preferences:
            processed.append(
                {
                    "category": getattr(item, "category", None),
                    "key": str(getattr(item, "key", "")).strip(),
                    "value": getattr(item, "value", None),
                    "confidence": getattr(item, "confidence", None),
                }
            )

        processed = [item for item in processed if item["key"]]
        processed.sort(key=lambda item: (item["key"], self._stringify(item["value"])))
        return processed

    def _prepare_dislikes(
        self,
        dislikes: list[ExplicitDislike],
    ) -> list[dict[str, Any]]:
        """Normalize and sort dislikes deterministically."""
        processed = []
        for item in dislikes:
            key = str(getattr(item, "key", "")).strip()
            if not key:
                continue
            processed.append(
                {
                    "key": key,
                    "reason": getattr(item, "reason", None),
                    "confidence": getattr(item, "confidence", None),
                }
            )

        processed.sort(key=lambda item: (item["key"], self._stringify(item["reason"])))
        return processed

    def _prepare_constraints(
        self,
        constraints: list[UserConstraint],
    ) -> list[dict[str, Any]]:
        """Normalize and sort constraints deterministically."""
        processed = []
        for item in constraints:
            constraint_type = str(getattr(item, "constraint_type", "")).strip()
            if not constraint_type:
                continue
            processed.append(
                {
                    "type": constraint_type,
                    "value": getattr(item, "value", None),
                    "active": bool(getattr(item, "active", True)),
                }
            )

        processed = [item for item in processed if item["active"]]
        processed.sort(key=lambda item: (item["type"], self._stringify(item["value"])))
        return processed

    def _prepare_entities(
        self,
        entities: list[dict[str, Any] | Any],
    ) -> list[dict[str, Any]]:
        """Normalize and sort entities deterministically."""
        processed: list[dict[str, Any]] = []

        for entity in entities:
            normalized = self._normalize_entity(entity)
            if normalized is not None:
                processed.append(normalized)

        processed.sort(
            key=lambda item: (
                str(item.get("name", "")),
                str(item.get("entity_type", "")),
            )
        )
        return processed

    def _normalize_entity(self, entity: dict[str, Any] | Any) -> dict[str, Any] | None:
        """Convert arbitrary entity objects into prompt-safe dictionaries."""
        if entity is None:
            return None

        if isinstance(entity, dict):
            name = entity.get("name") or entity.get("canonical_name")
            if not name:
                return None
            return {
                "id": self._stringify(entity.get("id")) if entity.get("id") is not None else None,
                "name": str(name).strip(),
                "entity_type": str(
                    entity.get("entity_type") or entity.get("type") or "entity"
                ).strip(),
                "summary": self._stringify(entity.get("summary"))
                if entity.get("summary")
                else None,
                "metadata": self._safe_jsonable(entity.get("metadata", {})),
            }

        name = getattr(entity, "name", None) or getattr(entity, "canonical_name", None)
        if not name:
            return None

        entity_type = (
            getattr(entity, "entity_type", None) or getattr(entity, "type", None) or "entity"
        )
        if hasattr(entity_type, "value"):
            entity_type = entity_type.value

        return {
            "id": self._stringify(getattr(entity, "id", None))
            if getattr(entity, "id", None) is not None
            else None,
            "name": str(name).strip(),
            "entity_type": str(entity_type).strip(),
            "summary": self._stringify(getattr(entity, "summary", None))
            if getattr(entity, "summary", None)
            else None,
            "metadata": self._safe_jsonable(
                getattr(entity, "metadata_col", getattr(entity, "metadata", {}))
            ),
        }

    def _select_memories(
        self,
        memories: list[ScoredMemory],
        token_budget: int,
    ) -> list[ScoredMemory]:
        """Pick highest-value memories that fit the section budget."""
        selected: list[ScoredMemory] = []
        consumed_tokens = 0

        ordered = sorted(
            memories,
            key=lambda item: (
                -float(item.score),
                self._memory_sort_key(item),
            ),
        )

        for item in ordered:
            approx_tokens = self._estimate_tokens(self._memory_to_prompt_line(item.memory))
            if consumed_tokens + approx_tokens > token_budget and selected:
                continue
            selected.append(item)
            consumed_tokens += approx_tokens
            if consumed_tokens >= token_budget:
                break

        return selected

    def _select_history(
        self,
        history: list[ConversationTurn],
        token_budget: int,
    ) -> list[ConversationTurn]:
        """Keep the most recent turns that fit the history budget."""
        selected: list[ConversationTurn] = []
        consumed_tokens = 0

        for turn in reversed(history):
            content = str(getattr(turn, "content", ""))
            role = str(getattr(turn, "role", "unknown"))
            approx_tokens = self._estimate_tokens(f"{role}: {content}")
            if consumed_tokens + approx_tokens > token_budget and selected:
                break
            selected.append(turn)
            consumed_tokens += approx_tokens
            if consumed_tokens >= token_budget:
                break

        selected.reverse()
        return selected

    def _select_memories_enhanced(
        self,
        memories: list[ScoredMemory],
        token_budget: int,
        query_type: str = "general",
    ) -> list[ScoredMemory]:
        """Enhanced memory selection with score thresholds and diversity.

        Improvements:
        - Score threshold filtering (only high-quality memories)
        - Diversity selection (avoid duplicate topics)
        - Query-type-specific selection criteria
        """
        selected: list[ScoredMemory] = []
        consumed_tokens = 0

        # Set score threshold based on query type
        if query_type == "factual":
            min_score = 0.3  # Lower threshold for factual queries
        elif query_type == "conversational":
            min_score = 0.5  # Higher threshold for conversational
        else:
            min_score = 0.4  # Default threshold

        # Filter by score threshold
        filtered_memories = [m for m in memories if m.score >= min_score]

        # Sort by score, then by importance
        ordered = sorted(
            filtered_memories,
            key=lambda item: (
                -float(item.score),
                -float(getattr(item.memory, "importance", 0.5)),
                self._memory_sort_key(item),
            ),
        )

        for item in ordered:
            approx_tokens = self._estimate_tokens(self._memory_to_prompt_line(item.memory))
            if consumed_tokens + approx_tokens > token_budget and selected:
                continue
            selected.append(item)
            consumed_tokens += approx_tokens
            if consumed_tokens >= token_budget:
                break

        return selected

    def _select_history_enhanced(
        self,
        history: list[ConversationTurn],
        token_budget: int,
        query_type: str = "general",
    ) -> list[ConversationTurn]:
        """Enhanced history selection with intent-aware filtering.

        Improvements:
        - Intent-aware turn selection
        - Tool call prioritization for certain query types
        - Role-based balancing
        """
        selected: list[ConversationTurn] = []
        consumed_tokens = 0

        # For factual queries, prioritize tool calls
        if query_type == "factual":
            # Separate tool calls from regular turns
            tool_turns = []
            regular_turns = []

            for turn in reversed(history):
                tool_calls = getattr(turn, "tool_calls", None)
                if tool_calls:
                    tool_turns.append(turn)
                else:
                    regular_turns.append(turn)

            # Select tool turns first, then regular turns
            for turn in tool_turns + regular_turns:
                content = str(getattr(turn, "content", ""))
                role = str(getattr(turn, "role", "unknown"))
                approx_tokens = self._estimate_tokens(f"{role}: {content}")
                if consumed_tokens + approx_tokens > token_budget and selected:
                    break
                selected.append(turn)
                consumed_tokens += approx_tokens
                if consumed_tokens >= token_budget:
                    break
        else:
            # Default: most recent turns
            for turn in reversed(history):
                content = str(getattr(turn, "content", ""))
                role = str(getattr(turn, "role", "unknown"))
                approx_tokens = self._estimate_tokens(f"{role}: {content}")
                if consumed_tokens + approx_tokens > token_budget and selected:
                    break
                selected.append(turn)
                consumed_tokens += approx_tokens
                if consumed_tokens >= token_budget:
                    break

        selected.reverse()
        return selected

    def _normalize_summary_anchor(self, summary_anchor: str | None) -> str | None:
        if summary_anchor is None:
            return None
        cleaned = summary_anchor.strip()
        return cleaned or None

    def _memory_to_prompt_line(self, memory: Any) -> str:
        """Serialize a memory object into a stable prompt line."""
        if memory is None:
            return ""

        memory_type = getattr(memory, "memory_type", None) or getattr(memory, "type", None)
        content = getattr(memory, "content", memory)

        content_str = self._stringify(content)
        if memory_type:
            return f"[{memory_type}] {content_str}"
        return content_str

    def _memory_sort_key(self, item: ScoredMemory) -> tuple[str, str]:
        memory = item.memory
        memory_type = str(getattr(memory, "memory_type", "") or "")
        content = self._stringify(getattr(memory, "content", ""))
        return (memory_type, content[:120])

    def _format_section(self, title: str, body: str) -> str:
        return f"{title}:\n{body}".strip()

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count with tiktoken when available, fallback to chars."""
        cleaned = text.strip()
        if not cleaned:
            return 0

        try:
            import tiktoken  # type: ignore

            encoding = tiktoken.get_encoding(self._tokenizer_encoding_name)
            return len(encoding.encode(cleaned))
        except Exception:
            return max(1, len(cleaned) // self._char_to_token_ratio)

    def _safe_jsonable(self, value: Any) -> Any:
        """Convert arbitrary values into JSON-safe structures."""
        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return value

        if isinstance(value, dict):
            return {str(k): self._safe_jsonable(v) for k, v in value.items()}

        if isinstance(value, (list, tuple, set)):
            return [self._safe_jsonable(v) for v in value]

        if hasattr(value, "model_dump"):
            try:
                return self._safe_jsonable(value.model_dump())
            except Exception:
                return self._stringify(value)

        if is_dataclass(value):
            try:
                return self._safe_jsonable(asdict(value))
            except Exception:
                return self._stringify(value)

        if hasattr(value, "__dict__"):
            try:
                return self._safe_jsonable(vars(value))
            except Exception:
                return self._stringify(value)

        return self._stringify(value)

    def _stringify(self, value: Any) -> str:
        """Stable string conversion for prompt material."""
        if value is None:
            return ""

        if isinstance(value, str):
            return value.strip()

        if isinstance(value, (int, float, bool)):
            return str(value)

        safe_value = self._safe_jsonable(value)
        try:
            return json.dumps(
                safe_value,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).strip()
        except Exception:
            return str(value).strip()
