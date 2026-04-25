from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_CONTENT_TYPE = "application/problem+json"
BASE_URI = "https://docs.butler.lasmoid.ai/problems"


class Problem(Exception):
    """RFC 9457 Problem Details exception."""

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
        self.type = type if type.startswith("http") else f"{BASE_URI}/{type}"
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
        if self.detail is not None:
            body["detail"] = self.detail

        resolved_instance = instance or self.instance
        if resolved_instance is not None:
            body["instance"] = resolved_instance

        if self.extensions:
            body.update(self.extensions)

        return body


def _problem_headers(
    request: Request, extra_headers: dict[str, str] | None = None
) -> dict[str, str]:
    headers: dict[str, str] = {}

    request_id = getattr(request.state, "request_id", None)
    if request_id:
        headers["X-Request-ID"] = str(request_id)

    if extra_headers:
        headers.update(extra_headers)

    return headers


async def problem_exception_handler(request: Request, exc: Problem) -> JSONResponse:
    """Render a Problem instance as an RFC 9457 response."""
    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict(instance=str(request.url.path)),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=_problem_headers(request),
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """Map Starlette HTTP exceptions into RFC 9457 responses."""
    problem = Problem(
        type="http-error",
        title="HTTP Error",
        status=exc.status_code,
        detail=str(exc.detail) if exc.detail is not None else None,
    )
    return JSONResponse(
        status_code=problem.status,
        content=problem.to_dict(instance=str(request.url.path)),
        media_type=PROBLEM_CONTENT_TYPE,
        headers=_problem_headers(request, exc.headers),
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Map validation failures into RFC 9457 responses.

    Keep the response useful for clients but do not echo raw request bodies or
    other debug-heavy internals back to callers.
    """
    normalized_errors = [
        {
            "loc": list(error.get("loc", [])),
            "msg": error.get("msg"),
            "type": error.get("type"),
        }
        for error in exc.errors()
    ]

    problem = Problem(
        type="validation-error",
        title="Request Validation Failed",
        status=422,
        detail="The request payload was structurally invalid.",
        validation_errors=normalized_errors,
    )
    return await problem_exception_handler(request, problem)


class NotFoundProblem(Problem):
    def __init__(self, resource: str, resource_id: str | None = None) -> None:
        detail = f"{resource} not found"
        if resource_id is not None:
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
    def __init__(
        self,
        detail: str = "You do not have permission to perform this action.",
    ) -> None:
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


class ApprovalRequiredProblem(Problem):
    def __init__(self, approval_type: str, detail: str) -> None:
        super().__init__(
            type="approval-required",
            title="Approval Required",
            status=409,
            detail=detail,
            approval_type=approval_type,
        )


class InternalError(Problem):
    def __init__(self, detail: str = "An unexpected error occurred.") -> None:
        super().__init__(
            type="internal-error",
            title="Internal Server Error",
            status=500,
            detail=detail,
        )


class ServiceUnavailableProblem(Problem):
    def __init__(
        self,
        detail: str = "The service is currently under high load or maintenance.",
    ) -> None:
        super().__init__(
            type="service-unavailable",
            title="Service Unavailable",
            status=503,
            detail=detail,
        )


class GatewayErrors:
    @staticmethod
    def unhealthy_node() -> ServiceUnavailableProblem:
        return ServiceUnavailableProblem(
            detail="This cluster node is currently unhealthy and cannot process requests safely."
        )
