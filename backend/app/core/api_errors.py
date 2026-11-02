"""Uniform error shape for the Open API and hosted flow.

    { "error": { "type": "invalid_request" | "authentication" | "permission" | "not_found"
                         | "conflict" | "rate_limit" | "provider" | "api",
                 "code": "consent_revoked", "message": "...", "param": "nin" } }
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

_TYPES = {
    400: "invalid_request",
    401: "authentication",
    402: "billing",
    403: "permission",
    404: "not_found",
    409: "conflict",
    410: "gone",
    413: "invalid_request",
    422: "invalid_request",
    429: "rate_limit",
    502: "provider",
    503: "provider",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, param: str | None = None,
                 details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.param, self.details = status, code, message, param, details

    def body(self) -> dict[str, object]:
        err: dict[str, object] = {"type": _TYPES.get(self.status, "api"), "code": self.code, "message": self.message}
        if self.param:
            err["param"] = self.param
        if self.details:
            err["details"] = self.details
        return {"error": err}


async def api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(status_code=exc.status, content=exc.body())
