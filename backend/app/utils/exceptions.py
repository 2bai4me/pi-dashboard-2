"""Zentrale Fehlerbehandlung und Exception-Definitionen.

Jeder Service wirft definierte Exceptions, die vom globalen Exception-Handler
in main.py abgefangen und in einheitliche HTTP-Responses umgewandelt werden.

Hierarchie:
  DashboardError (Base)
  ├── AuthError           → 401 Unauthorized
  │   ├── InvalidTokenError
  │   ├── TokenExpiredError
  │   └── InsufficientPermissionsError  → 403 Forbidden
  ├── NotFoundError       → 404 Not Found
  │   ├── TaskNotFoundError
  │   ├── ProjectNotFoundError
  │   ├── SopNotFoundError
  │   └── InstanceNotFoundError
  ├── ValidationError     → 422 Unprocessable Entity
  │   ├── InvalidInputError
  │   └── MissingFieldError
  ├── ConflictError       → 409 Conflict
  │   └── DuplicateEntryError
  ├── ServiceError        → 500 Internal Server Error
  │   ├── DatabaseError
  │   ├── LlmError
  │   └── SubAgentError
  └── RateLimitError      → 429 Too Many Requests

Verwendung:
  from ..utils.exceptions import TaskNotFoundError, ValidationError
  
  raise TaskNotFoundError(task_id="123")
  raise ValidationError("Title is required")
"""
from __future__ import annotations

from typing import Optional, Any, Dict


class DashboardError(Exception):
    """Basis-Exception für alle Dashboard-Fehler."""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "detail": self.message,
            "status_code": self.status_code,
            "details": self.details,
        }


# === 401 Unauthorized ===

class AuthError(DashboardError):
    def __init__(self, message: str = "Authentication required", details: Optional[Dict] = None):
        super().__init__(message, status_code=401, details=details)


class InvalidTokenError(AuthError):
    def __init__(self, message: str = "Invalid or malformed token"):
        super().__init__(message, details={"token_type": "invalid"})


class TokenExpiredError(AuthError):
    def __init__(self, message: str = "Token has expired"):
        super().__init__(message, details={"token_type": "expired"})


class InsufficientPermissionsError(AuthError):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, details={"permission": "denied"})


# === 404 Not Found ===

class NotFoundError(DashboardError):
    def __init__(self, message: str = "Resource not found", details: Optional[Dict] = None):
        super().__init__(message, status_code=404, details=details)


class TaskNotFoundError(NotFoundError):
    def __init__(self, task_id: str):
        super().__init__(f"Task {task_id} not found", details={"task_id": task_id})


class ProjectNotFoundError(NotFoundError):
    def __init__(self, project_id: str):
        super().__init__(f"Project {project_id} not found", details={"project_id": project_id})


class SopNotFoundError(NotFoundError):
    def __init__(self, sop_id: str):
        super().__init__(f"SOP {sop_id} not found", details={"sop_id": sop_id})


class InstanceNotFoundError(NotFoundError):
    def __init__(self, instance_id: str):
        super().__init__(f"SOP Instance {instance_id} not found", details={"instance_id": instance_id})


# === 422 Unprocessable Entity ===

class ValidationError(DashboardError):
    def __init__(self, message: str = "Validation failed", details: Optional[Dict] = None):
        super().__init__(message, status_code=422, details=details)


class InvalidInputError(ValidationError):
    def __init__(self, field: str, reason: str):
        super().__init__(
            f"Invalid input for '{field}': {reason}",
            details={"field": field, "reason": reason},
        )


class MissingFieldError(ValidationError):
    def __init__(self, field: str):
        super().__init__(f"Missing required field: '{field}'", details={"field": field})


# === 409 Conflict ===

class ConflictError(DashboardError):
    def __init__(self, message: str = "Conflict", details: Optional[Dict] = None):
        super().__init__(message, status_code=409, details=details)


class DuplicateEntryError(ConflictError):
    def __init__(self, entity: str, key: str):
        super().__init__(
            f"{entity} with key '{key}' already exists",
            details={"entity": entity, "key": key},
        )


# === 500 Internal Server Error ===

class ServiceError(DashboardError):
    def __init__(self, message: str = "Internal service error", details: Optional[Dict] = None):
        super().__init__(message, status_code=500, details=details)


class DatabaseError(ServiceError):
    def __init__(self, message: str = "Database operation failed", details: Optional[Dict] = None):
        super().__init__(message, details=details)


class LlmError(ServiceError):
    def __init__(self, message: str = "LLM call failed", details: Optional[Dict] = None):
        super().__init__(message, details=details)


class SubAgentError(ServiceError):
    def __init__(self, message: str = "Sub-agent spawn failed", details: Optional[Dict] = None):
        super().__init__(message, details=details)


# === 429 Too Many Requests ===

class RateLimitError(DashboardError):
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict] = None):
        super().__init__(message, status_code=429, details=details)
