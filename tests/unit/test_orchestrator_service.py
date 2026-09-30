from dataclasses import dataclass, field
from uuid import UUID

import pytest

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
    ExtractionServiceError,
    PersistenceServiceError,
    ValidationServiceError,
)

CORRELATION_ID = "8f6f7c3e-12d5-4f57-9c6c-123456789abc"
REQUEST = PdfRequestSchema(
    archivo_base64="JVBERi0xLjQK...",
    nombre="contrato.pdf",
)
VALIDATION_RESULT = ValidationSuccessSchema(
    valido=True,
    nombre="contrato.pdf",
    tamano_bytes=245760,
)
EXTRACTION_RESULT = ExtractionResponseSchema(
    nombre="contrato-extraido.pdf",
    texto="Texto extraído del documento",
    checksum="sha256-extraido",
    tamano_bytes=245760,
    paginas=3,
)
EXPECTED_PERSISTENCE_REQUEST = PersistenceCreateRequestSchema(
    nombre="contrato-extraido.pdf",
    texto="Texto extraído del documento",
    checksum="sha256-extraido",
    tamano_bytes=245760,
    paginas=3,
)
CREATED_DOCUMENT = PdfDocumentResponseSchema(
    id=UUID(CORRELATION_ID),
    nombre="contrato-extraido.pdf",
    texto="Texto extraído del documento",
    checksum="sha256-extraido",
    tamano_bytes=245760,
    paginas=3,
    created_at="2026-09-14T18:00:00Z",
    updated_at="2026-09-14T18:00:00Z",
)


def service_error(code: str, message: str) -> ServiceErrorSchema:
    return ServiceErrorSchema(
        code=code,
        message=message,
        details={},
        correlation_id=UUID(CORRELATION_ID),
    )


@dataclass
class FakeValidationPort:
    result: ValidationSuccessSchema | Exception = field(
        default_factory=lambda: VALIDATION_RESULT.model_copy()
    )
    calls: list[tuple[PdfRequestSchema, str]] = field(default_factory=list)
    events: list[str] | None = None

    def validate(
        self,
        request: PdfRequestSchema,
        correlation_id: str,
    ) -> ValidationSuccessSchema:
        self.calls.append((request, correlation_id))
        if self.events is not None:
            self.events.append("validation")
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class FakeExtractionPort:
    result: ExtractionResponseSchema | Exception = field(
        default_factory=lambda: EXTRACTION_RESULT.model_copy()
    )
    calls: list[tuple[PdfRequestSchema, str]] = field(default_factory=list)
    events: list[str] | None = None

    def extract(
        self,
        request: PdfRequestSchema,
        correlation_id: str,
    ) -> ExtractionResponseSchema:
        self.calls.append((request, correlation_id))
        if self.events is not None:
            self.events.append("extraction")
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class FakePersistenceUpdatesPort:
    result: PdfDocumentResponseSchema | Exception = field(
        default_factory=lambda: CREATED_DOCUMENT.model_copy()
    )
    calls: list[
        tuple[PersistenceCreateRequestSchema, str]
    ] = field(default_factory=list)
    events: list[str] | None = None

    def create(
        self,
        request: PersistenceCreateRequestSchema,
        correlation_id: str,
    ) -> PdfDocumentResponseSchema:
        self.calls.append((request, correlation_id))
        if self.events is not None:
            self.events.append("persistence")
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def build_orchestrator(
    validation: FakeValidationPort,
    extraction: FakeExtractionPort,
    persistence: FakePersistenceUpdatesPort,
) -> OrchestratorService:
    return OrchestratorService(
        validation_service=validation,
        extraction_service=extraction,
        persistence_service=persistence,
    )


def test_successful_flow_returns_created_document_in_dependency_order() -> None:
    events: list[str] = []
    validation = FakeValidationPort(events=events)
    extraction = FakeExtractionPort(events=events)
    persistence = FakePersistenceUpdatesPort(events=events)
    service = build_orchestrator(validation, extraction, persistence)

    result = service.orchestrate(REQUEST, correlation_id=CORRELATION_ID)

    assert result == CREATED_DOCUMENT
    assert events == ["validation", "extraction", "persistence"]


def test_extraction_result_builds_the_persistence_creation_request() -> None:
    validation = FakeValidationPort()
    extraction = FakeExtractionPort()
    persistence = FakePersistenceUpdatesPort()
    service = build_orchestrator(validation, extraction, persistence)

    service.orchestrate(REQUEST, correlation_id=CORRELATION_ID)

    assert persistence.calls[0][0] == EXPECTED_PERSISTENCE_REQUEST


def test_same_correlation_id_is_propagated_to_all_ports() -> None:
    validation = FakeValidationPort()
    extraction = FakeExtractionPort()
    persistence = FakePersistenceUpdatesPort()
    service = build_orchestrator(validation, extraction, persistence)

    service.orchestrate(REQUEST, correlation_id=CORRELATION_ID)

    assert validation.calls[0][1] == CORRELATION_ID
    assert extraction.calls[0][1] == CORRELATION_ID
    assert persistence.calls[0][1] == CORRELATION_ID


def test_validation_error_propagates_without_calling_later_ports() -> None:
    error = ValidationServiceError(service_error("PDF_INVALID", "invalid PDF"))
    validation = FakeValidationPort(result=error)
    extraction = FakeExtractionPort()
    persistence = FakePersistenceUpdatesPort()
    service = build_orchestrator(validation, extraction, persistence)

    with pytest.raises(ValidationServiceError) as raised:
        service.orchestrate(REQUEST, correlation_id=CORRELATION_ID)

    assert raised.value is error
    assert extraction.calls == []
    assert persistence.calls == []


def test_extraction_error_propagates_without_calling_persistence() -> None:
    error = ExtractionServiceError(
        service_error("PDF_CORRUPTED", "extraction failed")
    )
    validation = FakeValidationPort()
    extraction = FakeExtractionPort(result=error)
    persistence = FakePersistenceUpdatesPort()
    service = build_orchestrator(validation, extraction, persistence)

    with pytest.raises(ExtractionServiceError) as raised:
        service.orchestrate(REQUEST, correlation_id=CORRELATION_ID)

    assert raised.value is error
    assert persistence.calls == []


def test_persistence_error_propagates_without_saga_compensation() -> None:
    error = PersistenceServiceError(
        service_error("DATABASE_ERROR", "persistence failed")
    )
    validation = FakeValidationPort()
    extraction = FakeExtractionPort()
    persistence = FakePersistenceUpdatesPort(result=error)
    service = build_orchestrator(validation, extraction, persistence)

    with pytest.raises(PersistenceServiceError) as raised:
        service.orchestrate(REQUEST, correlation_id=CORRELATION_ID)

    assert raised.value is error
    assert len(persistence.calls) == 1
