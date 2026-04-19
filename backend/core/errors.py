"""RFC 9457 Problem Details for HTTP APIs.

Every error in Butler MUST use this model. No custom error envelopes.
Reference: https://www.rfc-editor.org/rfc/rfc9457
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


PROBLEM_CONTENT_TYPE = "application/problem+json"
BASE_URI = "https://docs.butler.lasmoid.ai/problems"


class Problem(Exception):
    """RFC 9457 Problem Details exception.

    Usage:
        raise Problem(
            type="invalid-credentials",
            title="Invalid Credentials",
            status=401,
            detail="The email or password provided is incorrect.",
        )
    """

    def __init__(
        self,
        *,
        type: str,  # noqa: A002
        title: str,
        status: int,
        detail: str | None = None,
        instance: str | None = None,
        **extensions: Any,
    ) -> None:
        self.type = f"{BASE_URI}/{type}" if not type.startswith("http") else type
        self.title = title
        self.status = status
        self.detail = detail
        self.instance = instance
        self.extensions = extensions
        super().__init__(title)

    def to_dict(self, instance: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
        }
        if self.detail:
            body["detail"] = self.detail
        if instance or self.instance:
            body["instance"] = instance or self.instance
        body.update(self.extensions)
        return body


async def problem_exception_handler(request: Request, exc: Problem) -> JSONResponse:
    """Global FastAPI exception handler for Problem instances."""
    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict(instance=str(request.url.path)),
        media_type=PROBLEM_CONTENT_TYPE,
        headers={
            "X-Request-ID": getattr(request.state, "request_id", ""),
        },
    )

from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError

async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Catches standard HTTP Exceptions and forces them into RFC 9457 shape."""
    problem = Problem(
        type="http-error",
        title="HTTP Error",
        status=exc.status_code,
        detail=str(exc.detail)
    )
    return await problem_exception_handler(request, problem)

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Catches FastAPI Pydantic errors and forces them into RFC 9457 shape."""
    problem = Problem(
        type="validation-error",
        title="Request Validation Failed",
        status=422,
        detail="The request payload was structurally invalid.",
        validation_errors=exc.errors()
    )
    return await problem_exception_handler(request, problem)

# ---------------------------------------------------------------------------
# Shared problem factories — used across services
# ---------------------------------------------------------------------------

class NotFoundProblem(Problem):
    def __init__(self, resource: str, resource_id: str | None = None) -> None:
        detail = f"{resource} not found"
        if resource_id:
            detail = f"{resource} '{resource_id}' not found"
        super().__init__(
            type="not-found",
            title="Resource Not Found",
            status=404,
            detail=detail,
        )


class ValidationProblem(Problem):
    def __init__(self, detail: str, fields: dict[str, str] | None = None) -> None:
        super().__init__(
            type="validation-error",
            title="Validation Error",
            status=422,
            detail=detail,
            **({"fields": fields} if fields else {}),
        )


class ForbiddenProblem(Problem):
    def __init__(self, detail: str = "You do not have permission to perform this action.") -> None:
        super().__init__(
            type="forbidden",
            title="Forbidden",
            status=403,
            detail=detail,
        )


class ConflictProblem(Problem):
    def __init__(self, detail: str) -> None:
        super().__init__(
            type="conflict",
            title="Conflict",
            status=409,
            detail=detail,
        )


class InternalError(Problem):
    def __init__(self, detail: str = "An unexpected error occurred.") -> None:
        super().__init__(
            type="internal-error",
            title="Internal Server Error",
            status=500,
            detail=detail,
        )
