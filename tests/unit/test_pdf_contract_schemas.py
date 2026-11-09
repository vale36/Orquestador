import base64
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.schemas.pdf_schemas import (
    MAX_PDF_BASE64_LENGTH,
    MAX_PDF_SIZE_BYTES,
    ErrorResponseSchema,
    PdfDocumentResponseSchema,
    PdfRequestSchema,
)


def test_pdf_request_requires_contract_fields_and_accepts_json_types() -> None:
    archivo_base64 = base64.b64encode(b"%PDF-1.4\n").decode("ascii")
    request = PdfRequestSchema(archivo_base64=archivo_base64, nombre="contrato.pdf")

    assert request.archivo_base64 == archivo_base64
    assert request.nombre == "contrato.pdf"

    with pytest.raises(ValidationError):
        PdfRequestSchema(archivo_base64=archivo_base64)

    with pytest.raises(ValidationError):
        PdfRequestSchema(archivo_base64=123, nombre="contrato.pdf")

    with pytest.raises(ValidationError, match="Base64 válido"):
        PdfRequestSchema(archivo_base64="not!base64", nombre="contrato.pdf")


def test_pdf_request_accepts_exactly_the_maximum_decoded_size() -> None:
    archivo_base64 = base64.b64encode(b"x" * MAX_PDF_SIZE_BYTES).decode("ascii")

    request = PdfRequestSchema(archivo_base64=archivo_base64, nombre="contrato.pdf")

    assert len(base64.b64decode(request.archivo_base64)) == MAX_PDF_SIZE_BYTES


def test_pdf_request_rejects_encoded_data_over_the_maximum_size() -> None:
    archivo_base64 = "A" * (MAX_PDF_BASE64_LENGTH + 1)

    with pytest.raises(ValidationError) as error:
        PdfRequestSchema(archivo_base64=archivo_base64, nombre="contrato.pdf")

    assert error.value.errors()[0]["type"] == "pdf_too_large"


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
    assert body["created_at"] == "2026-09-14T18:00:00.000Z"


def test_document_response_dates_have_milliseconds_like_persistence() -> None:
    """A15: la respuesta coincide con la de persistencia-actualizaciones."""
    moment = datetime(2026, 10, 7, 14, 3, 47, 787654, tzinfo=UTC)
    document = PdfDocumentResponseSchema(
        id=UUID("8f6f7c3e-12d5-4f57-9c6c-123456789abc"),
        nombre="contrato.pdf",
        checksum="abc",
        texto="Texto",
        tamano_bytes=1,
        paginas=1,
        created_at=moment,
        updated_at=moment,
    )

    body = document.model_dump(mode="json")

    assert body["created_at"] == "2026-10-07T14:03:47.787Z"
    assert body["updated_at"] == "2026-10-07T14:03:47.787Z"


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
