"""Ports for external services used by the orchestrator.

The public PDF creation flow does not query documents, so no
persistence-query port is defined until a required workflow needs one.
"""

from typing import Protocol, runtime_checkable

from app.schemas.pdf_schemas import (
    ExtractionResponseSchema,
    PdfDocumentResponseSchema,
    PdfRequestSchema,
    PersistenceCreateRequestSchema,
    ServiceErrorSchema,
    ValidationSuccessSchema,
)


class ExternalServiceError(Exception):
    """An external service returned an error from the shared error contract."""

    def __init__(self, error: ServiceErrorSchema) -> None:
        self.error = error
        super().__init__(error.message)


class DependencyUnavailableError(ExternalServiceError):
    """An external dependency could not be reached or used."""


class ValidationServiceError(ExternalServiceError):
    """The validation service rejected or could not validate a document."""


class ExtractionServiceError(ExternalServiceError):
    """The extraction service rejected or could not process a document."""


class PersistenceServiceError(ExternalServiceError):
    """The persistence service could not complete a document operation."""


@runtime_checkable
class ValidationPort(Protocol):
    """Validates the supplied PDF request.

    Receives the JSON request fields ``archivo_base64`` and ``nombre`` and
    returns the validation service's success schema. It must forward the
    correlation ID unchanged. Contract failures raise ``ValidationServiceError``;
    dependency failures raise ``DependencyUnavailableError``.
    """

    def validate(
        self,
        request: PdfRequestSchema,
        correlation_id: str,
    ) -> ValidationSuccessSchema:
        ...


@runtime_checkable
class ExtractionPort(Protocol):
    """Requests text extraction and checksum generation for a PDF.

    Receives the PDF request fields and returns the extraction response schema.
    It must forward the correlation ID unchanged. Contract failures raise
    ``ExtractionServiceError``; dependency failures raise
    ``DependencyUnavailableError``.
    """

    def extract(
        self,
        request: PdfRequestSchema,
        correlation_id: str,
    ) -> ExtractionResponseSchema:
        ...


@runtime_checkable
class PersistenceUpdatesPort(Protocol):
    """Creates a document using the persistence-updates service.

    Receives the document data required by the shared persistence create
    contract, returns the created document response, and forwards the
    correlation ID unchanged. Contract failures raise
    ``PersistenceServiceError``; dependency failures raise
    ``DependencyUnavailableError``.
    """

    def create(
        self,
        request: PersistenceCreateRequestSchema,
        correlation_id: str,
    ) -> PdfDocumentResponseSchema:
        ...

    def compensate(
        self,
        checksum: str,
        correlation_id: str,
    ) -> None:
        """Undo persistence for a checksum; repeated calls are safe.

        If the resource no longer exists, compensation succeeds without
        performing another deletion.
        """
        ...
