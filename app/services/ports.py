"""Puertos hacia los otros microservicios. Las implementaciones HTTP viven en
app/core/ y los tests usan dobles en memoria inyectados por el mismo mecanismo."""

from abc import ABC, abstractmethod
from uuid import UUID

from app.models.pdf_document import ExtractionResult, PdfDocument, PdfRequest


class ValidationPort(ABC):
    @abstractmethod
    async def validate(self, request: PdfRequest, correlation_id: str) -> None: ...


class ExtractionPort(ABC):
    @abstractmethod
    async def extract(
        self, request: PdfRequest, correlation_id: str
    ) -> ExtractionResult: ...


class PersistenceUpdatesPort(ABC):
    @abstractmethod
    async def create(
        self, extraction: ExtractionResult, correlation_id: str
    ) -> PdfDocument: ...

    @abstractmethod
    async def delete(self, document_id: UUID, correlation_id: str) -> None: ...


class PersistenceQueriesPort(ABC):
    @abstractmethod
    async def find_by_checksum(
        self, checksum: str, correlation_id: str
    ) -> PdfDocument | None: ...
