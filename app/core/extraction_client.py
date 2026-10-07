from dataclasses import asdict, replace

from app.core.document_mapping import extraction_result_from_json
from app.core.json_http_client import JsonHttpClient
from app.models.pdf_document import ExtractionResult, PdfRequest
from app.services.ports import ExtractionPort


class ExtractionHttpClient(ExtractionPort):
    def __init__(self, http: JsonHttpClient) -> None:
        self._http = http

    async def extract(
        self, request: PdfRequest, correlation_id: str
    ) -> ExtractionResult:
        body, headers = await self._http.request_with_headers(
            "POST", "/extraer", correlation_id, json=asdict(request)
        )
        result = extraction_result_from_json(body, "extraccion-texto")
        return replace(
            result,
            extraction_time_ms=_milliseconds(headers.get("X-Extraction-Time-Ms")),
        )


def _milliseconds(value: str | None) -> float | None:
    """El tiempo es informativo: si falta o no es un número, se ignora."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
