from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator


class PdfRequestSchema(BaseModel):
    archivo_base64: str
    nombre: str


class ValidationSuccessSchema(BaseModel):
    valido: Literal[True]
    nombre: str
    tamano_bytes: int


class ServiceErrorSchema(BaseModel):
    code: str
    message: str
    details: dict[str, object]
    correlation_id: UUID


class ValidationFailureSchema(BaseModel):
    valido: Literal[False]
    error: ServiceErrorSchema


class ExtractionResponseSchema(BaseModel):
    nombre: str
    texto: str
    checksum: str
    tamano_bytes: int
    paginas: int


class PersistenceCreateRequestSchema(BaseModel):
    nombre: str
    checksum: str
    texto: str
    tamano_bytes: int
    paginas: int


class PdfDocumentResponseSchema(BaseModel):
    id: UUID
    nombre: str
    checksum: str
    texto: str
    tamano_bytes: int
    paginas: int
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def require_iso8601_string(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("timestamp must be an ISO-8601 string")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_utc_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must use UTC")
        return value


class ErrorResponseSchema(BaseModel):
    error: ServiceErrorSchema
