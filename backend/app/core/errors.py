from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: Any = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_error"


class PermissionDenied(AppError):
    status_code = 403
    code = "forbidden"


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthorized"


class InsufficientStock(AppError):
    status_code = 409
    code = "insufficient_stock"


class TooManyRequests(AppError):
    status_code = 429
    code = "rate_limited"
