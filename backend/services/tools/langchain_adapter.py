"""LangChain adapter for Butler-governed tools.

LangChain is an optional integration surface. Butler remains the authority for
tool policy, audit, idempotency, and execution. This module only projects
ButlerToolSpec entries into LangChain BaseTool objects when the optional
`agentic` dependency group is installed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any

from pydantic import BaseModel, PrivateAttr

from domain.tools.contracts import ToolResult, ToolsServiceContract
from domain.tools.hermes_compiler import ButlerToolSpec

try:
    from langchain_core.tools import BaseTool
except ImportError as exc:  # pragma: no cover - depends on optional extra.
    BaseTool = object  # type: ignore[assignment, misc]
    _LANGCHAIN_IMPORT_ERROR: ImportError | None = exc
else:  # pragma: no cover - exercised only when optional extra is installed.
    _LANGCHAIN_IMPORT_ERROR = None


IdempotencyKeyFactory = Callable[[ButlerToolSpec, dict[str, Any]], str | None]


class ButlerLangChainUnavailableError(RuntimeError):
    """Raised when LangChain adapters are requested without the optional extra."""


ButlerLangChainUnavailable = ButlerLangChainUnavailableError


class ButlerToolAdapter(BaseTool):  # type: ignore[misc, valid-type]
    """Expose one Butler-governed tool as a LangChain BaseTool."""

    name: str
    description: str
    args_schema: type[BaseModel] | None = None

    _spec: ButlerToolSpec = PrivateAttr()
    _executor: ToolsServiceContract = PrivateAttr()
    _account_id: str = PrivateAttr()
    _session_id: str | None = PrivateAttr(default=None)
    _idempotency_key_factory: IdempotencyKeyFactory | None = PrivateAttr(default=None)

    def __init__(
        self,
        *,
        spec: ButlerToolSpec,
        executor: ToolsServiceContract,
        account_id: str,
        session_id: str | None = None,
        idempotency_key_factory: IdempotencyKeyFactory | None = None,
    ) -> None:
        _ensure_langchain_available()
        super().__init__(
            name=spec.name,
            description=spec.description or spec.name,
        )
        self._spec = spec
        self._executor = executor
        self._account_id = account_id
        self._session_id = session_id
        self._idempotency_key_factory = idempotency_key_factory

    def _run(self, **kwargs: Any) -> str:
        """Reject sync execution so policy/audit remains on async Butler paths."""
        raise RuntimeError("Butler LangChain tools must be executed asynchronously.")

    async def _arun(self, **kwargs: Any) -> str:
        """Execute through Butler's tool executor, never directly through LangChain."""
        idempotency_key = kwargs.pop("_idempotency_key", None)
        if idempotency_key is None and self._idempotency_key_factory is not None:
            idempotency_key = self._idempotency_key_factory(self._spec, kwargs)

        result = await self._executor.execute(
            tool_name=self._spec.name,
            params=dict(kwargs),
            account_id=self._account_id,
            session_id=self._session_id,
            idempotency_key=idempotency_key,
        )
        return _serialize_tool_result(result)


def langchain_available() -> bool:
    """Return whether the optional LangChain tool dependency is importable."""
    return _LANGCHAIN_IMPORT_ERROR is None


def build_langchain_tools(
    specs: Iterable[ButlerToolSpec],
    *,
    executor: ToolsServiceContract,
    account_id: str,
    session_id: str | None = None,
    idempotency_key_factory: IdempotencyKeyFactory | None = None,
) -> list[ButlerToolAdapter]:
    """Wrap visible, unblocked Butler tool specs as LangChain tools."""
    _ensure_langchain_available()
    return [
        ButlerToolAdapter(
            spec=spec,
            executor=executor,
            account_id=account_id,
            session_id=session_id,
            idempotency_key_factory=idempotency_key_factory,
        )
        for spec in specs
        if not spec.blocked
    ]


def _ensure_langchain_available() -> None:
    if _LANGCHAIN_IMPORT_ERROR is not None:
        raise ButlerLangChainUnavailableError(
            "LangChain tool adapters require the optional 'agentic' dependency group."
        ) from _LANGCHAIN_IMPORT_ERROR


def _serialize_tool_result(result: ToolResult) -> str:
    payload = {
        "success": result.success,
        "tool_name": result.tool_name,
        "execution_id": result.execution_id,
        "data": result.data,
        "verification": result.verification.model_dump(mode="json"),
        "compensation": result.compensation,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)
