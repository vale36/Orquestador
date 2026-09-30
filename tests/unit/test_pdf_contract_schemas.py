from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.pdf_schemas import (
    ErrorResponseSchema,
    ExtractionResponseSchema,
    PdfDocumentResponseSchema,
    PdfRequestSchema,
    PersistenceCreateRequestSchema,
    ValidationFailureSchema,
    ValidationSuccessSchema,
)


def test_pdf_request_requires_contract_fields_and_accepts_json_types() -> None:
    request = PdfRequestSchema(
        archivo_base64="JVBERi0xLjQK...",
        nombre="contrato.pdf",
    )

    assert request.archivo_base64 == "JVBERi0xLjQK..."
    assert request.nombre == "contrato.pdf"

    with pytest.raises(ValidationError):
        PdfRequestSchema(archivo_base64="JVBERi0xLjQK...")

    with pytest.raises(ValidationError):
        PdfRequestSchema(archivo_base64=123, nombre="contrato.pdf")


def test_validation_response_matches_shared_validation_contract() -> None:
    response = ValidationSuccessSchema.model_validate(
        {"valido": True, "nombre": "contrato.pdf", "tamano_bytes": 245760}
    )

    assert response.valido is True
    assert response.nombre == "contrato.pdf"
    assert response.tamano_bytes == 245760


def test_extraction_and_persistence_schemas_match_shared_contracts() -> None:
    extraction = ExtractionResponseSchema.model_validate(
        {
            "nombre": "contrato.pdf",
            "texto": "Contenido extraído del PDF",
            "checksum": "a7f5f35426b927411fc9231b56382173",
            "tamano_bytes": 245760,
            "paginas": 3,
        }
    )
    persistence_request = PersistenceCreateRequestSchema.model_validate(
        {
            "nombre": extraction.nombre,
            "checksum": extraction.checksum,
            "texto": extraction.texto,
            "tamano_bytes": extraction.tamano_bytes,
            "paginas": extraction.paginas,
        }
    )

    assert extraction.nombre == persistence_request.nombre
    assert extraction.checksum == persistence_request.checksum
    assert extraction.texto == persistence_request.texto
    assert extraction.tamano_bytes == persistence_request.tamano_bytes
    assert extraction.paginas == persistence_request.paginas


def test_document_response_requires_uuid_and_utc_iso8601_timestamps() -> None:
    response = PdfDocumentResponseSchema.model_validate(
        {
            "id": "8f6f7c3e-12d5-4f57-9c6c-123456789abc",
            "nombre": "contrato.pdf",
            "checksum": "a7f5f35426b927411fc9231b56382173",
            "texto": "Contenido extraído del PDF",
            "tamano_bytes": 245760,
            "paginas": 3,
            "created_at": "2026-09-14T18:00:00Z",
            "updated_at": "2026-09-14T18:00:00+00:00",
        }
    )

    assert response.id == UUID("8f6f7c3e-12d5-4f57-9c6c-123456789abc")
    assert isinstance(response.created_at, datetime)
    assert response.created_at.utcoffset().total_seconds() == 0
    assert response.updated_at.utcoffset().total_seconds() == 0

    invalid_document = {
        "id": "not-a-uuid",
        "nombre": "contrato.pdf",
        "checksum": "checksum",
        "texto": "Contenido",
        "tamano_bytes": 245760,
        "paginas": 3,
        "created_at": "2026-09-14T18:00:00",
        "updated_at": "2026-09-14T18:00:00Z",
    }
    with pytest.raises(ValidationError):
        PdfDocumentResponseSchema.model_validate(invalid_document)

    invalid_document["id"] = "8f6f7c3e-12d5-4f57-9c6c-123456789abc"
    invalid_document["created_at"] = "2026-09-14T18:00:00+01:00"
    with pytest.raises(ValidationError):
        PdfDocumentResponseSchema.model_validate(invalid_document)


def test_error_responses_match_shared_error_contract() -> None:
    error_payload = {
        "error": {
            "code": "PDF_INVALID",
            "message": "El archivo no es un PDF válido",
            "details": {},
            "correlation_id": "8f6f7c3e-12d5-4f57-9c6c-123456789abc",
        }
    }
    response = ErrorResponseSchema.model_validate(error_payload)
    validation_failure = ValidationFailureSchema.model_validate(
        {
            "valido": False,
            **error_payload,
        }
    )

    assert response.error.code == "PDF_INVALID"
    assert response.error.message == "El archivo no es un PDF válido"
    assert response.error.details == {}
    assert response.error.correlation_id == UUID(
        "8f6f7c3e-12d5-4f57-9c6c-123456789abc"
    )
    assert validation_failure.valido is False
    assert validation_failure.error == response.error
