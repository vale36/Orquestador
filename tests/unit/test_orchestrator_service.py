from dataclasses import dataclass
from typing import Any

import pytest

from app.services.orchestrator import OrchestratorService


@dataclass
class FakeValidationService:
    result: Any
    calls: list[tuple[dict[str, Any], str]]

    def validate(self, request: dict[str, Any], correlation_id: str) -> Any:
        self.calls.append((request, correlation_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class FakeExtractionService:
    result: Any
    calls: list[tuple[dict[str, Any], str]]

    def extract(self, request: dict[str, Any], correlation_id: str) -> Any:
        self.calls.append((request, correlation_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class FakePersistenceService:
    result: Any
    calls: list[tuple[dict[str, Any], str]]

    def create(self, request: dict[str, Any], correlation_id: str) -> Any:
        self.calls.append((request, correlation_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class FakeCompensationService:
    calls: list[tuple[dict[str, Any], str]]

    def compensate(self, request: dict[str, Any], correlation_id: str) -> None:
        self.calls.append((request, correlation_id))


def build_orchestrator(
    validation: FakeValidationService,
    extraction: FakeExtractionService,
    persistence: FakePersistenceService,
    compensation: FakeCompensationService,
) -> OrchestratorService:
    return OrchestratorService(
        validation_service=validation,
        extraction_service=extraction,
        persistence_service=persistence,
        compensation_service=compensation,
    )


def test_orchestrates_successful_pdf_flow_and_returns_created_document() -> None:
    request = {"archivo_base64": "JVBERi0xLjQK...", "nombre": "contrato.pdf"}
    created_document = {
        "id": "document-id",
        "nombre": "contrato.pdf",
        "checksum": "checksum",
        "texto": "Texto extraído",
        "tamano_bytes": 1024,
        "paginas": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    validation = FakeValidationService(result={"estado": "OK"}, calls=[])
    extraction = FakeExtractionService(
        result={"texto": "Texto extraído", "checksum": "checksum"},
        calls=[],
    )
    persistence = FakePersistenceService(result=created_document, calls=[])
    compensation = FakeCompensationService(calls=[])
    service = build_orchestrator(validation, extraction, persistence, compensation)

    result = service.orchestrate(request, correlation_id="corr-123")

    assert result == created_document
    assert len(validation.calls) == 1
    assert len(extraction.calls) == 1
    assert len(persistence.calls) == 1
    assert compensation.calls == []


def test_requests_saga_compensation_when_persistence_fails() -> None:
    request = {"archivo_base64": "JVBERi0xLjQK...", "nombre": "contrato.pdf"}
    persistence_error = RuntimeError("persistence unavailable")
    validation = FakeValidationService(result={"estado": "OK"}, calls=[])
    extraction = FakeExtractionService(result={"estado": "OK"}, calls=[])
    persistence = FakePersistenceService(result=persistence_error, calls=[])
    compensation = FakeCompensationService(calls=[])
    service = build_orchestrator(validation, extraction, persistence, compensation)

    with pytest.raises(RuntimeError, match="persistence unavailable"):
        service.orchestrate(request, correlation_id="corr-123")

    assert len(compensation.calls) == 1
    assert compensation.calls[0][1] == "corr-123"


def test_propagates_correlation_id_to_all_dependencies() -> None:
    request = {"archivo_base64": "JVBERi0xLjQK...", "nombre": "contrato.pdf"}
    validation = FakeValidationService(result={"estado": "OK"}, calls=[])
    extraction = FakeExtractionService(result={"estado": "OK"}, calls=[])
    persistence = FakePersistenceService(result={"id": "document-id"}, calls=[])
    compensation = FakeCompensationService(calls=[])
    service = build_orchestrator(validation, extraction, persistence, compensation)

    service.orchestrate(request, correlation_id="corr-456")

    assert validation.calls[0][1] == "corr-456"
    assert extraction.calls[0][1] == "corr-456"
    assert persistence.calls[0][1] == "corr-456"


def test_does_not_continue_when_validation_fails() -> None:
    request = {"archivo_base64": "invalid", "nombre": "contrato.pdf"}
    validation_error = ValueError("invalid PDF")
    validation = FakeValidationService(result=validation_error, calls=[])
    extraction = FakeExtractionService(result={"estado": "OK"}, calls=[])
    persistence = FakePersistenceService(result={"id": "document-id"}, calls=[])
    compensation = FakeCompensationService(calls=[])
    service = build_orchestrator(validation, extraction, persistence, compensation)

    with pytest.raises(ValueError, match="invalid PDF"):
        service.orchestrate(request, correlation_id="corr-789")

    assert extraction.calls == []
    assert persistence.calls == []


def test_does_not_persist_when_extraction_fails() -> None:
    request = {"archivo_base64": "JVBERi0xLjQK...", "nombre": "contrato.pdf"}
    extraction_error = RuntimeError("extraction unavailable")
    validation = FakeValidationService(result={"estado": "OK"}, calls=[])
    extraction = FakeExtractionService(result=extraction_error, calls=[])
    persistence = FakePersistenceService(result={"id": "document-id"}, calls=[])
    compensation = FakeCompensationService(calls=[])
    service = build_orchestrator(validation, extraction, persistence, compensation)

    with pytest.raises(RuntimeError, match="extraction unavailable"):
        service.orchestrate(request, correlation_id="corr-999")

    assert persistence.calls == []
