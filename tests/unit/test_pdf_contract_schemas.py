from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.pdf_schemas import (
    ErrorResponseSchema,
    PdfDocumentResponseSchema,
    PdfRequestSchema,
)


def test_pdf_request_requires_contract_fields_and_accepts_json_types() -> None:
    request = PdfRequestSchema(archivo_base64="JVBERi0xLjQK...", nombre="contrato.pdf")

    assert request.archivo_base64 == "JVBERi0xLjQK..."
    assert request.nombre == "contrato.pdf"

    with pytest.raises(ValidationError):
        PdfRequestSchema(archivo_base64="JVBERi0xLjQK...")

    with pytest.raises(ValidationError):
        PdfRequestSchema(archivo_base64=123, nombre="contrato.pdf")


def test_document_response_serializes_the_common_model() -> None:
    document = PdfDocumentResponseSchema(
        id=UUID("8f6f7c3e-12d5-4f57-9c6c-123456789abc"),
        nombre="contrato.pdf",
        checksum="abc",
        texto="Texto",
        tamano_bytes=1,
        paginas=1,
        created_at=datetime(2026, 9, 14, 18, 0, tzinfo=UTC),
        updated_at=datetime(2026, 9, 14, 18, 0, tzinfo=UTC),
    )

    body = document.model_dump(mode="json")

    assert body["id"] == "8f6f7c3e-12d5-4f57-9c6c-123456789abc"
    assert body["created_at"] == "2026-09-14T18:00:00Z"


def test_error_responses_match_shared_error_contract() -> None:
    response = ErrorResponseSchema.model_validate(
        {
            "error": {
                "code": "PDF_INVALID",
                "message": "El archivo no es un PDF válido",
                "details": {},
                "correlation_id": "8f6f7c3e-12d5-4f57-9c6c-123456789abc",
            }
        }
    )

    assert response.error.code == "PDF_INVALID"
    assert response.error.correlation_id == UUID("8f6f7c3e-12d5-4f57-9c6c-123456789abc")
