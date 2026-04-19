from opentelemetry import trace
from functools import wraps

tracer = trace.get_tracer("butler")

def traced(span_name: str, attributes: dict = None):
    """Decorator to trace a function with Butler semantic conventions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("butler.status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("butler.status", "error")
                    span.set_attribute("error.class", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator
