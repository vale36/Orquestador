from app.clients._http_json_client import HttpJsonClient
from app.schemas.pdf_schemas import (
    ExtractionResponseSchema,
    PdfRequestSchema,
)
from app.services.ports import ExtractionServiceError


class ExtractionHttpClient(HttpJsonClient):
    def __init__(self) -> None:
        super().__init__("EXTRACCION_URL", "extraction service")

    def extract(
        self,
        request: PdfRequestSchema,
        correlation_id: str,
    ) -> ExtractionResponseSchema:
        return self.post_json(
            "/extraer",
            request.model_dump(mode="json"),
            correlation_id,
            ExtractionResponseSchema,
            ExtractionServiceError,
        )
