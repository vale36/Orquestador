from dataclasses import asdict

from app.core.document_mapping import extraction_result_from_json
from app.core.json_http_client import JsonHttpClient
from app.models.pdf_document import ExtractionResult, PdfRequest


class ExtractionHttpClient:
    def __init__(self, http: JsonHttpClient) -> None:
        self._http = http

    async def extract(
        self, request: PdfRequest, correlation_id: str
    ) -> ExtractionResult:
        body = await self._http.request(
            "POST", "/extraer", correlation_id, json=asdict(request)
        )
        return extraction_result_from_json(body, "extraccion-texto")
