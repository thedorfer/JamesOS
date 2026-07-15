from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class ErrorCodeSpec:
    category: str
    severity: str
    retryable: bool
    user_message: str


ERROR_CODES: Mapping[str, ErrorCodeSpec] = MappingProxyType({
    "CONFIG_MISSING": ErrorCodeSpec("configuration", "error", False, "Required configuration is missing."),
    "CONFIG_INVALID": ErrorCodeSpec("configuration", "error", False, "Configuration is invalid."),
    "SECRET_FILE_MISSING": ErrorCodeSpec("configuration", "error", False, "A required secret is not configured."),
    "SECRET_FILE_PERMISSIONS_INVALID": ErrorCodeSpec("configuration", "error", False, "Secret-file permissions are unsafe."),
    "ARTIFACT_NOT_FOUND": ErrorCodeSpec("artifact", "error", False, "The required artifact was not found."),
    "ARTIFACT_SHA_MISMATCH": ErrorCodeSpec("artifact", "error", False, "Artifact integrity verification failed."),
    "APPROVAL_MISSING": ErrorCodeSpec("approval", "warning", False, "Required approval is missing."),
    "APPROVAL_STALE": ErrorCodeSpec("approval", "warning", False, "The approval no longer matches the artifact."),
    "STATE_CONFLICT": ErrorCodeSpec("state", "warning", False, "The operation conflicts with current state."),
    "FONT_RESOURCE_NOT_FOUND": ErrorCodeSpec("font_acquisition", "error", False, "The configured font resource could not be found."),
    "FONT_LICENSE_INVALID": ErrorCodeSpec("font_acquisition", "error", False, "The configured font license could not be verified."),
    "FONT_FAMILY_MISMATCH": ErrorCodeSpec("font_acquisition", "error", False, "The downloaded font did not match its configuration."),
    "FONT_ACQUISITION_INCOMPLETE": ErrorCodeSpec("font_acquisition", "error", True, "Font acquisition did not complete."),
    "HTTP_UNAUTHORIZED": ErrorCodeSpec("authentication", "error", False, "Authentication with the external service failed."),
    "HTTP_FORBIDDEN": ErrorCodeSpec("authorization", "error", False, "The external service denied this operation."),
    "HTTP_NOT_FOUND": ErrorCodeSpec("external_dependency", "error", False, "The requested external resource was not found."),
    "HTTP_RATE_LIMITED": ErrorCodeSpec("external_dependency", "warning", True, "The external service rate limit was reached."),
    "HTTP_SERVER_ERROR": ErrorCodeSpec("external_dependency", "error", True, "The external service is temporarily unavailable."),
    "PRINTIFY_UPLOAD_FAILED": ErrorCodeSpec("printify", "error", False, "The Printify upload failed."),
    "PRINTIFY_PRODUCT_CREATE_FAILED": ErrorCodeSpec("printify", "error", False, "The Printify product draft could not be created."),
    "COMFYUI_JOB_FAILED": ErrorCodeSpec("comfyui", "error", True, "ComfyUI processing failed."),
    "FILESYSTEM_WRITE_FAILED": ErrorCodeSpec("filesystem", "error", False, "JamesOS could not write a required file."),
    "VALIDATION_FAILED": ErrorCodeSpec("validation", "warning", False, "Validation failed."),
    "UNEXPECTED_INTERNAL_ERROR": ErrorCodeSpec("internal", "critical", False, "An unexpected internal error occurred."),
})


class JamesOSError(Exception):
    def __init__(self, code: str, *, diagnostic_message: str = "", operation: str = "unknown", stage: str = "unknown",
                 category: str | None = None, severity: str | None = None, user_message: str | None = None,
                 retryable: bool | None = None, context: dict[str, Any] | None = None, state: dict[str, Any] | None = None,
                 suggested_action: str = "Review the diagnostic record and correct the reported condition.", cause: BaseException | None = None) -> None:
        spec = ERROR_CODES.get(code)
        if spec is None: raise ValueError(f"Unknown JamesOS error code: {code}")
        self.code, self.category, self.severity = code, category or spec.category, severity or spec.severity
        self.user_message = user_message or spec.user_message
        self.diagnostic_message = diagnostic_message or self.user_message
        self.operation, self.stage = operation, stage
        self.retryable = spec.retryable if retryable is None else retryable
        self.context, self.state = dict(context or {}), dict(state or {})
        self.suggested_action, self.original_cause = suggested_action, cause
        super().__init__(self.diagnostic_message)


class ConfigurationError(JamesOSError): pass
class ValidationError(JamesOSError): pass
class ApprovalError(JamesOSError): pass
class ArtifactIntegrityError(JamesOSError): pass
class ExternalDependencyError(JamesOSError): pass
class NetworkError(JamesOSError): pass
class ComfyUIError(JamesOSError): pass
class PrintifyError(JamesOSError): pass
class FontAcquisitionError(JamesOSError): pass
class FilesystemError(JamesOSError): pass
class StateConflictError(JamesOSError): pass
class UnexpectedJamesOSError(JamesOSError): pass


def unexpected_error(exc: BaseException, *, operation: str, stage: str = "boundary", context: dict[str, Any] | None = None,
                     state: dict[str, Any] | None = None) -> UnexpectedJamesOSError:
    return UnexpectedJamesOSError("UNEXPECTED_INTERNAL_ERROR", diagnostic_message=f"{type(exc).__name__}: {exc}",
        operation=operation, stage=stage, context=context, state=state, cause=exc,
        suggested_action="Use the error ID to inspect the protected diagnostic record.")
