"""Domain errors."""

from __future__ import annotations


class DomainError(Exception):
    code: str = "DOMAIN_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code
        self.message = message


class NotFoundError(DomainError):
    code = "NOT_FOUND"


class ConflictError(DomainError):
    code = "CONFLICT"


class AuthenticationError(DomainError):
    code = "AUTHENTICATION_FAILED"


class AuthorizationError(DomainError):
    code = "FORBIDDEN"


class ValidationDomainError(DomainError):
    code = "VALIDATION_ERROR"


class WriteOperationForbiddenError(DomainError):
    code = "WRITE_OPERATION_FORBIDDEN"


class SecretVaultError(DomainError):
    code = "SECRET_VAULT_ERROR"


class DiscoveryError(DomainError):
    code = "DISCOVERY_ERROR"
