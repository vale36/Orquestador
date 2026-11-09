"""Contrato HTTP público del orquestador (microservicios-pdf v1.0.0)."""

import base64
import binascii
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, field_serializer, field_validator
from pydantic_core import PydanticCustomError

MAX_PDF_SIZE_BYTES = 5 * 1024 * 1024
MAX_PDF_BASE64_LENGTH = 4 * ((MAX_PDF_SIZE_BYTES + 2) // 3)
MAX_REQUEST_BODY_BYTES = MAX_PDF_BASE64_LENGTH + 4096


class PdfRequestSchema(BaseModel):
    archivo_base64: str
    nombre: str

    @field_validator("archivo_base64")
    @classmethod
    def validate_pdf_base64(cls, value: str) -> str:
        if len(value) > MAX_PDF_BASE64_LENGTH:
            raise PydanticCustomError(
                "pdf_too_large", "El PDF supera el tamaño máximo permitido"
            )
        try:
            pdf_bytes = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("archivo_base64 debe ser Base64 válido") from error
        if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
            raise PydanticCustomError(
                "pdf_too_large", "El PDF supera el tamaño máximo permitido"
            )
        return value


class PdfDocumentResponseSchema(BaseModel):
    id: UUID
    nombre: str
    checksum: str
    texto: str
    tamano_bytes: int
    paginas: int
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _iso_utc_milliseconds(self, moment: datetime) -> str:
        """Mismo formato que persistencia (A15): milisegundos y sufijo Z."""
        iso = moment.astimezone(UTC).isoformat(timespec="milliseconds")
        return iso.replace("+00:00", "Z")


class ServiceErrorSchema(BaseModel):
    code: str
    message: str
    details: dict[str, object]
    correlation_id: UUID


class ErrorResponseSchema(BaseModel):
    error: ServiceErrorSchema
