from app.clients._http_json_client import HttpJsonClient
from app.schemas.pdf_schemas import (
    PdfDocumentResponseSchema,
    PersistenceCreateRequestSchema,
)
from app.services.ports import PersistenceServiceError


class PersistenceUpdatesHttpClient(HttpJsonClient):
    def __init__(self) -> None:
        super().__init__(
            "PERSISTENCIA_ACTUALIZACIONES_URL",
            "persistence updates service",
        )

    def create(
        self,
        request: PersistenceCreateRequestSchema,
        correlation_id: str,
    ) -> PdfDocumentResponseSchema:
        return self.post_json(
            "/pdf",
            request.model_dump(mode="json"),
            correlation_id,
            PdfDocumentResponseSchema,
            PersistenceServiceError,
        )
