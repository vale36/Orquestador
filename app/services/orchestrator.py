import logging

from app.schemas.pdf_schemas import (
    PdfDocumentResponseSchema,
    PdfRequestSchema,
    PersistenceCreateRequestSchema,
)
from app.services.ports import (
    ExtractionPort,
    PersistenceUpdatesPort,
    ValidationPort,
)

logger = logging.getLogger(__name__)


class OrchestratorService:
    def __init__(
        self,
        validation_service: ValidationPort,
        extraction_service: ExtractionPort,
        persistence_service: PersistenceUpdatesPort,
    ) -> None:
        self._validation_service = validation_service
        self._extraction_service = extraction_service
        self._persistence_service = persistence_service

    def orchestrate(
        self,
        request: PdfRequestSchema,
        correlation_id: str,
    ) -> PdfDocumentResponseSchema:
        self._validation_service.validate(request, correlation_id)
        extraction_result = self._extraction_service.extract(
            request,
            correlation_id,
        )
        persistence_request = PersistenceCreateRequestSchema(
            nombre=extraction_result.nombre,
            checksum=extraction_result.checksum,
            texto=extraction_result.texto,
            tamano_bytes=extraction_result.tamano_bytes,
            paginas=extraction_result.paginas,
        )
        try:
            return self._persistence_service.create(
                persistence_request,
                correlation_id,
            )
        except Exception:
            logger.warning(
                "Attempting SAGA compensation checksum=%s correlation_id=%s",
                persistence_request.checksum,
                correlation_id,
            )
            try:
                self._persistence_service.compensate(
                    persistence_request.checksum,
                    correlation_id,
                )
            except Exception as compensation_error:
                logger.error(
                    "SAGA compensation failed checksum=%s correlation_id=%s "
                    "error_type=%s",
                    persistence_request.checksum,
                    correlation_id,
                    type(compensation_error).__name__,
                )
            else:
                logger.info(
                    "SAGA compensation completed checksum=%s "
                    "correlation_id=%s result=success",
                    persistence_request.checksum,
                    correlation_id,
                )
            raise
