import logging

from app.models.pdf_document import PdfDocument, PdfRequest
from app.services.ports import (
    ExtractionPort,
    PersistenceQueriesPort,
    PersistenceUpdatesPort,
    ValidationPort,
)

logger = logging.getLogger(__name__)


class OrchestratorService:
    def __init__(
        self,
        validation_service: ValidationPort,
        extraction_service: ExtractionPort,
        persistence_updates: PersistenceUpdatesPort,
        persistence_queries: PersistenceQueriesPort,
    ) -> None:
        self._validation_service = validation_service
        self._extraction_service = extraction_service
        self._persistence_updates = persistence_updates
        self._persistence_queries = persistence_queries

    async def orchestrate(
        self, request: PdfRequest, correlation_id: str
    ) -> PdfDocument:
        await self._validation_service.validate(request, correlation_id)
        extraction = await self._extraction_service.extract(request, correlation_id)
        try:
            return await self._persistence_updates.create(extraction, correlation_id)
        except Exception:
            logger.warning(
                "Attempting SAGA compensation checksum=%s correlation_id=%s",
                extraction.checksum,
                correlation_id,
            )
            try:
                await self._compensate(extraction.checksum, correlation_id)
            except Exception as compensation_error:
                logger.error(
                    "SAGA compensation failed checksum=%s correlation_id=%s "
                    "error_type=%s",
                    extraction.checksum,
                    correlation_id,
                    type(compensation_error).__name__,
                )
            else:
                logger.info(
                    "SAGA compensation completed checksum=%s correlation_id=%s",
                    extraction.checksum,
                    correlation_id,
                )
            raise

    async def _compensate(self, checksum: str, correlation_id: str) -> None:
        """Borra el documento con ese checksum si existe. Idempotente: si no está,
        no hay nada que deshacer."""
        document = await self._persistence_queries.find_by_checksum(
            checksum, correlation_id
        )
        if document is not None:
            await self._persistence_updates.delete(document.id, correlation_id)
