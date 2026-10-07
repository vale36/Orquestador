"""Contrato HTTP público del orquestador (microservicios-pdf v1.0.0)."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, field_serializer


class PdfRequestSchema(BaseModel):
    archivo_base64: str
    nombre: str


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
