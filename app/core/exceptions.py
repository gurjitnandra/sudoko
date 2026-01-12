"""Domain-specific exception classes."""
from __future__ import annotations


class DomainError(Exception):
    """Base class for predictable business rule violations."""


class AuthenticationError(DomainError):
    """Raised when authentication fails."""


class BadRequestError(DomainError):
    """Raised when the request contains invalid data."""


class AuthorizationError(DomainError):
    """Raised when a user is not allowed to perform an action."""


class InsufficientCreditsError(DomainError):
    """Raised when a wallet lacks required credits."""


class ConflictError(DomainError):
    """Raised when attempting an invalid state transition."""
