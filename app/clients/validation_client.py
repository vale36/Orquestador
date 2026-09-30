from app.clients._http_json_client import HttpJsonClient
from app.schemas.pdf_schemas import (
    PdfRequestSchema,
    ValidationSuccessSchema,
)
from app.services.ports import ValidationServiceError


class ValidationHttpClient(HttpJsonClient):
    def __init__(self) -> None:
        super().__init__("VALIDACION_URL", "validation service")

    def validate(
        self,
        request: PdfRequestSchema,
        correlation_id: str,
    ) -> ValidationSuccessSchema:
        return self.post_json(
            "/validar",
            request.model_dump(mode="json"),
            correlation_id,
            ValidationSuccessSchema,
            ValidationServiceError,
        )
