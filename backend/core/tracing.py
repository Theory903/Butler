from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from typing import Any, ParamSpec, TypeVar, overload

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, Tracer

P = ParamSpec("P")
R = TypeVar("R")

AttributeValue = str | bool | int | float
AttributeMap = Mapping[str, AttributeValue | None]
DynamicAttributeFactory = Callable[..., Mapping[str, Any]]


def get_tracer(name: str = "butler") -> Tracer:
    """Return the Butler tracer."""
    return trace.get_tracer(name)


# Backward-compatible module-level tracer export.
# A lot of code still does `from core.tracing import tracer`
# because humans enjoy keeping old imports alive forever.
tracer: Tracer = get_tracer()


def _safe_attribute_value(value: Any) -> AttributeValue | None:
    """Normalize values to OpenTelemetry-safe scalar attributes.

    Unsupported values are stringified defensively rather than crashing tracing.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        return value
    return str(value)


def _set_span_attributes(span: Span, attributes: Mapping[str, Any] | None) -> None:
    """Set span attributes defensively."""
    if not attributes:
        return

    for key, raw_value in attributes.items():
        if not key:
            continue

        value = _safe_attribute_value(raw_value)
        if value is None:
            continue

        try:
            span.set_attribute(str(key), value)
        except Exception:
            # tracing should never break business logic
            continue


def _bind_call_args(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Bind args/kwargs to function signature for dynamic attribute extraction."""
    try:
        signature = inspect.signature(func)
        bound = signature.bind_partial(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except Exception:
        return {"args": args, "kwargs": kwargs}


def _resolve_dynamic_attributes(
    factory: DynamicAttributeFactory | None,
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Safely resolve runtime attributes from the call."""
    if factory is None:
        return {}

    try:
        bound = _bind_call_args(func, args, kwargs)
        produced = factory(**bound)
        if isinstance(produced, Mapping):
            return dict(produced)
    except TypeError:
        try:
            produced = factory(*args, **kwargs)
            if isinstance(produced, Mapping):
                return dict(produced)
        except Exception:
            return {}
    except Exception:
        return {}

    return {}


def _default_span_name(func: Callable[..., Any]) -> str:
    """Derive a stable default span name from the callable."""
    module = getattr(func, "__module__", None) or "unknown"
    qualname = getattr(func, "__qualname__", None) or getattr(func, "__name__", "call")
    return f"{module}.{qualname}"


@overload
def traced(
    span_name: str | None = None,
    *,
    attributes: AttributeMap | None = None,
    dynamic_attributes: DynamicAttributeFactory | None = None,
    tracer: Tracer | None = None,
    record_result: bool = False,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]: ...


@overload
def traced(
    span_name: str | None = None,
    *,
    attributes: AttributeMap | None = None,
    dynamic_attributes: DynamicAttributeFactory | None = None,
    tracer: Tracer | None = None,
    record_result: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def traced(
    span_name: str | None = None,
    *,
    attributes: AttributeMap | None = None,
    dynamic_attributes: DynamicAttributeFactory | None = None,
    tracer: Tracer | None = None,
    record_result: bool = False,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to trace sync or async functions with Butler conventions."""
    chosen_tracer = tracer or get_tracer()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        resolved_span_name = span_name or _default_span_name(func)
        is_async = inspect.iscoroutinefunction(func)

        static_attributes = dict(attributes or {})

        if is_async:

            @wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
                with chosen_tracer.start_as_current_span(resolved_span_name) as span:
                    _set_span_attributes(
                        span,
                        {
                            "code.function": getattr(func, "__qualname__", func.__name__),
                            "code.module": getattr(func, "__module__", "unknown"),
                            "butler.status": "started",
                            **static_attributes,
                            **_resolve_dynamic_attributes(dynamic_attributes, func, args, kwargs),
                        },
                    )

                    try:
                        result = await func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        span.set_attribute("butler.status", "success")

                        if record_result:
                            result_value = _safe_attribute_value(result)
                            if result_value is not None:
                                span.set_attribute("butler.result", result_value)

                        return result
                    except Exception as exc:
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                        span.set_attribute("butler.status", "error")
                        span.set_attribute("error.type", type(exc).__name__)
                        span.set_attribute("error.message", str(exc))
                        span.record_exception(exc)
                        raise

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            with chosen_tracer.start_as_current_span(resolved_span_name) as span:
                _set_span_attributes(
                    span,
                    {
                        "code.function": getattr(func, "__qualname__", func.__name__),
                        "code.module": getattr(func, "__module__", "unknown"),
                        "butler.status": "started",
                        **static_attributes,
                        **_resolve_dynamic_attributes(dynamic_attributes, func, args, kwargs),
                    },
                )

                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    span.set_attribute("butler.status", "success")

                    if record_result:
                        result_value = _safe_attribute_value(result)
                        if result_value is not None:
                            span.set_attribute("butler.result", result_value)

                    return result
                except Exception as exc:
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.set_attribute("butler.status", "error")
                    span.set_attribute("error.type", type(exc).__name__)
                    span.set_attribute("error.message", str(exc))
                    span.record_exception(exc)
                    raise

        return sync_wrapper

    return decorator
