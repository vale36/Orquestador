"""Dobles de los puertos y datos de prueba compartidos por la suite."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from app.models.pdf_document import ExtractionResult, PdfDocument, PdfRequest
from app.services.orchestrator import OrchestratorService
from app.services.ports import (
    ExtractionPort,
    PersistenceQueriesPort,
    PersistenceUpdatesPort,
    ValidationPort,
)

CORRELATION_ID = "8f6f7c3e-12d5-4f57-9c6c-123456789abc"
DOCUMENT_ID = UUID("11111111-2222-3333-4444-555555555555")
REQUEST = PdfRequest(archivo_base64="JVBERi0xLjQK...", nombre="contrato.pdf")
EXTRACTION = ExtractionResult(
    nombre="contrato-extraido.pdf",
    texto="Texto extraído del documento",
    checksum="sha256-extraido",
    tamano_bytes=245760,
    paginas=3,
)
DOCUMENT = PdfDocument(
    id=DOCUMENT_ID,
    nombre="contrato-extraido.pdf",
    checksum="sha256-extraido",
    texto="Texto extraído del documento",
    tamano_bytes=245760,
    paginas=3,
    created_at=datetime(2026, 9, 14, 18, 0, tzinfo=UTC),
    updated_at=datetime(2026, 9, 14, 18, 0, tzinfo=UTC),
)


@dataclass
class FakeValidation(ValidationPort):
    error: Exception | None = None
    calls: list[tuple[PdfRequest, str]] = field(default_factory=list)

    async def validate(self, request: PdfRequest, correlation_id: str) -> None:
        self.calls.append((request, correlation_id))
        if self.error:
            raise self.error


@dataclass
class FakeExtraction(ExtractionPort):
    error: Exception | None = None
    result: ExtractionResult = EXTRACTION
    calls: list[tuple[PdfRequest, str]] = field(default_factory=list)

    async def extract(
        self, request: PdfRequest, correlation_id: str
    ) -> ExtractionResult:
        self.calls.append((request, correlation_id))
        if self.error:
            raise self.error
        return self.result


@dataclass
class FakePersistenceUpdates(PersistenceUpdatesPort):
    error: Exception | None = None
    delete_error: Exception | None = None
    create_calls: list[tuple[ExtractionResult, str]] = field(default_factory=list)
    delete_calls: list[tuple[UUID, str]] = field(default_factory=list)

    async def create(
        self, extraction: ExtractionResult, correlation_id: str
    ) -> PdfDocument:
        self.create_calls.append((extraction, correlation_id))
        if self.error:
            raise self.error
        return DOCUMENT

    async def delete(self, document_id: UUID, correlation_id: str) -> None:
        self.delete_calls.append((document_id, correlation_id))
        if self.delete_error:
            raise self.delete_error


@dataclass
class FakePersistenceQueries(PersistenceQueriesPort):
    document: PdfDocument | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def find_by_checksum(
        self, checksum: str, correlation_id: str
    ) -> PdfDocument | None:
        self.calls.append((checksum, correlation_id))
        return self.document


@dataclass
class Ports:
    validation: FakeValidation = field(default_factory=FakeValidation)
    extraction: FakeExtraction = field(default_factory=FakeExtraction)
    updates: FakePersistenceUpdates = field(default_factory=FakePersistenceUpdates)
    queries: FakePersistenceQueries = field(default_factory=FakePersistenceQueries)

    def service(self) -> OrchestratorService:
        return OrchestratorService(
            self.validation, self.extraction, self.updates, self.queries
        )
