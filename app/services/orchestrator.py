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
        return self._persistence_service.create(
            persistence_request,
            correlation_id,
        )
