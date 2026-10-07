from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class PdfDocument:
    id: UUID
    nombre: str
    checksum: str
    texto: str
    tamano_bytes: int
    paginas: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PdfRequest:
    archivo_base64: str
    nombre: str


@dataclass(frozen=True)
class ExtractionResult:
    nombre: str
    texto: str
    checksum: str
    tamano_bytes: int
    paginas: int
    # Tiempo que informa extraccion-texto; no es parte del documento.
    extraction_time_ms: float | None = None


@dataclass(frozen=True)
class OrchestrationResult:
    document: PdfDocument
    extraction_time_ms: float | None
