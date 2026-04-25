from __future__ import annotations

import pytest

from domain.tools.hermes_compiler import HermesToolCompiler
from services.tools.langchain_adapter import (
    ButlerLangChainUnavailable,
    build_langchain_tools,
    langchain_available,
)


def test_langchain_adapter_reports_optional_dependency_state() -> None:
    assert isinstance(langchain_available(), bool)


def test_build_langchain_tools_fails_clearly_without_optional_extra() -> None:
    if langchain_available():
        pytest.skip("LangChain optional dependency is installed in this environment.")

    spec = HermesToolCompiler().compile("get_time", {})

    with pytest.raises(ButlerLangChainUnavailable) as exc_info:
        build_langchain_tools(
            [spec],
            executor=object(),  # type: ignore[arg-type]
            account_id="03ab81ad-1849-4985-a69b-73079fdecc63",
        )

    assert "optional 'agentic' dependency group" in str(exc_info.value)
