from dataclasses import asdict

from app.core.json_http_client import JsonHttpClient
from app.models.pdf_document import PdfRequest


class ValidationHttpClient:
    def __init__(self, http: JsonHttpClient) -> None:
        self._http = http

    async def validate(self, request: PdfRequest, correlation_id: str) -> None:
        await self._http.request(
            "POST", "/validar", correlation_id, json=asdict(request)
        )
