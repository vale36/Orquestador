from app.core.document_mapping import document_from_json
from app.core.json_http_client import JsonHttpClient
from app.models.pdf_document import PdfDocument
from app.services.ports import PersistenceQueriesPort


class PersistenceQueriesHttpClient(PersistenceQueriesPort):
    def __init__(self, http: JsonHttpClient) -> None:
        self._http = http

    async def find_by_checksum(
        self, checksum: str, correlation_id: str
    ) -> PdfDocument | None:
        body = await self._http.request(
            "GET", f"/pdf/checksum/{checksum}", correlation_id, not_found_ok=True
        )
        return (
            None if body is None else document_from_json(body, "persistencia-consultas")
        )
