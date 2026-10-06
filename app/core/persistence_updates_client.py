from uuid import UUID

from app.core.document_mapping import document_from_json, extraction_result_to_json
from app.core.json_http_client import JsonHttpClient
from app.models.pdf_document import ExtractionResult, PdfDocument


class PersistenceUpdatesHttpClient:
    def __init__(self, http: JsonHttpClient) -> None:
        self._http = http

    async def create(
        self, extraction: ExtractionResult, correlation_id: str
    ) -> PdfDocument:
        # Sin reintentos: si el primer intento se guardó pero la respuesta se perdió,
        # reintentar daría 409. Ese caso lo resuelve la compensación SAGA.
        body = await self._http.request(
            "POST",
            "/pdf",
            correlation_id,
            json=extraction_result_to_json(extraction),
            retry=False,
        )
        return document_from_json(body, "persistencia-actualizaciones")

    async def delete(self, document_id: UUID, correlation_id: str) -> None:
        # 404 también es éxito: borrar algo que ya no existe deja el mismo estado.
        await self._http.request(
            "DELETE", f"/pdf/{document_id}", correlation_id, not_found_ok=True
        )
