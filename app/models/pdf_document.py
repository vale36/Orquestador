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
