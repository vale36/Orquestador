"""Contrato HTTP público del orquestador (microservicios-pdf v1.0.0)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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


class ServiceErrorSchema(BaseModel):
    code: str
    message: str
    details: dict[str, object]
    correlation_id: UUID


class ErrorResponseSchema(BaseModel):
    error: ServiceErrorSchema
