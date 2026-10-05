from typing import get_type_hints
from uuid import UUID

import app.services.ports as ports
from app.schemas.pdf_schemas import (
    ExtractionResponseSchema,
    PdfDocumentResponseSchema,
    PdfRequestSchema,
    PersistenceCreateRequestSchema,
    ServiceErrorSchema,
    ValidationSuccessSchema,
)
from app.services.orchestrator import OrchestratorService
from app.services.ports import (
    DependencyUnavailableError,
    ExtractionPort,
    ExtractionServiceError,
    ExternalServiceError,
    PersistenceServiceError,
    PersistenceUpdatesPort,
    ValidationPort,
    ValidationServiceError,
)


def test_service_dependencies_are_typed_against_ports() -> None:
    annotations = get_type_hints(OrchestratorService.__init__)

    assert annotations["validation_service"] is ValidationPort
    assert annotations["extraction_service"] is ExtractionPort
    assert annotations["persistence_service"] is PersistenceUpdatesPort
    assert "compensation_service" not in annotations
    assert not hasattr(ports, "PersistenceCompensationPort")


def test_ports_define_contract_payloads_responses_and_correlation_id() -> None:
    validation = get_type_hints(ValidationPort.validate)
    extraction = get_type_hints(ExtractionPort.extract)
    persistence = get_type_hints(PersistenceUpdatesPort.create)
    compensation = get_type_hints(PersistenceUpdatesPort.compensate)

    assert validation == {
        "request": PdfRequestSchema,
        "correlation_id": str,
        "return": ValidationSuccessSchema,
    }
    assert extraction == {
        "request": PdfRequestSchema,
        "correlation_id": str,
        "return": ExtractionResponseSchema,
    }
    assert persistence == {
        "request": PersistenceCreateRequestSchema,
        "correlation_id": str,
        "return": PdfDocumentResponseSchema,
    }
    assert compensation == {
        "checksum": str,
        "correlation_id": str,
        "return": type(None),
    }


def test_external_service_errors_preserve_contract_error_and_are_operation_specific() -> None:
    error = ServiceErrorSchema(
        code="DEPENDENCY_UNAVAILABLE",
        message="Servicio no disponible",
        details={},
        correlation_id=UUID("8f6f7c3e-12d5-4f57-9c6c-123456789abc"),
    )
    validation_error = ValidationServiceError(error)
    extraction_error = ExtractionServiceError(error)
    persistence_error = PersistenceServiceError(error)
    unavailable_error = DependencyUnavailableError(error)

    assert isinstance(validation_error, ExternalServiceError)
    assert isinstance(extraction_error, ExternalServiceError)
    assert isinstance(persistence_error, ExternalServiceError)
    assert isinstance(unavailable_error, ExternalServiceError)
    assert validation_error.error is error
    assert extraction_error.error is error
    assert persistence_error.error is error
    assert unavailable_error.error is error
    assert str(validation_error) == "Servicio no disponible"


def test_ports_are_structurally_implementable_by_test_doubles() -> None:
    class ValidationFake:
        def validate(
            self, request: PdfRequestSchema, correlation_id: str
        ) -> ValidationSuccessSchema:
            return ValidationSuccessSchema(
                valido=True,
                nombre=request.nombre,
                tamano_bytes=10,
            )

    class ExtractionFake:
        def extract(
            self, request: PdfRequestSchema, correlation_id: str
        ) -> ExtractionResponseSchema:
            return ExtractionResponseSchema(
                nombre=request.nombre,
                texto="contenido",
                checksum="checksum",
                tamano_bytes=10,
                paginas=1,
            )

    class PersistenceFake:
        def create(
            self, request: PersistenceCreateRequestSchema, correlation_id: str
        ) -> PdfDocumentResponseSchema:
            return PdfDocumentResponseSchema(
                id=UUID("8f6f7c3e-12d5-4f57-9c6c-123456789abc"),
                nombre=request.nombre,
                checksum=request.checksum,
                texto=request.texto,
                tamano_bytes=request.tamano_bytes,
                paginas=request.paginas,
                created_at="2026-09-14T00:00:00Z",
                updated_at="2026-09-14T00:00:00Z",
            )

        def compensate(
            self,
            checksum: str,
            correlation_id: str,
        ) -> None:
            return None

    validation = ValidationFake()
    extraction = ExtractionFake()
    persistence = PersistenceFake()

    assert isinstance(validation, ValidationPort)
    assert isinstance(extraction, ExtractionPort)
    assert isinstance(persistence, PersistenceUpdatesPort)
    pdf_request = PdfRequestSchema(archivo_base64="JVBERi0xLjQK...", nombre="a.pdf")
    assert validation.validate(pdf_request, "corr").valido
    extraction_result = extraction.extract(pdf_request, "corr")
    assert extraction_result.paginas == 1
    assert persistence.create(
        PersistenceCreateRequestSchema(
            nombre=extraction_result.nombre,
            checksum=extraction_result.checksum,
            texto=extraction_result.texto,
            tamano_bytes=extraction_result.tamano_bytes,
            paginas=extraction_result.paginas,
        ),
        "corr",
    ).nombre == "a.pdf"
