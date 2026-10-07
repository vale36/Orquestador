import logging
from datetime import UTC, datetime

from app.core.exceptions import DependencyUnavailableError
from app.models.pdf_document import OrchestrationResult, PdfRequest
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
    ) -> OrchestrationResult:
        # Al segundo: persistencia puede guardar created_at sin fracciones.
        started_at = datetime.now(UTC).replace(microsecond=0)
        await self._validation_service.validate(request, correlation_id)
        extraction = await self._extraction_service.extract(request, correlation_id)
        try:
            document = await self._persistence_updates.create(
                extraction, correlation_id
            )
        except DependencyUnavailableError:
            # Solo un alta sin respuesta deja una operación parcial posible: el
            # documento pudo guardarse aunque la respuesta no llegó. Un error del
            # contrato (409, 400, 422) significa que no se guardó nada.
            logger.warning(
                "Attempting SAGA compensation checksum=%s", extraction.checksum
            )
            try:
                await self._compensate(extraction.checksum, correlation_id, started_at)
            except Exception as compensation_error:
                logger.error(
                    "SAGA compensation failed checksum=%s error_type=%s",
                    extraction.checksum,
                    type(compensation_error).__name__,
                )
            raise
        return OrchestrationResult(
            document=document, extraction_time_ms=extraction.extraction_time_ms
        )

    async def _compensate(
        self, checksum: str, correlation_id: str, started_at: datetime
    ) -> None:
        """Borra el documento si lo creó esta request. Idempotente: si no existe, o
        existía desde antes, no hay nada que deshacer."""
        document = await self._persistence_queries.find_by_checksum(
            checksum, correlation_id
        )
        if document is None or document.created_at < started_at:
            logger.info(
                "SAGA compensation completed checksum=%s result=nothing-to-undo",
                checksum,
            )
            return
        await self._persistence_updates.delete(document.id, correlation_id)
        logger.info(
            "SAGA compensation completed checksum=%s result=deleted document_id=%s",
            checksum,
            document.id,
        )
