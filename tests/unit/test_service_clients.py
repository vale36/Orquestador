import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.core.exceptions import DependencyUnavailableError
from app.core.extraction_client import ExtractionHttpClient
from app.core.json_http_client import JsonHttpClient
from app.core.persistence_queries_client import PersistenceQueriesHttpClient
from app.core.persistence_updates_client import PersistenceUpdatesHttpClient
from app.core.validation_client import ValidationHttpClient
from app.models.pdf_document import ExtractionResult, PdfDocument, PdfRequest

CORRELATION_ID = "8f6f7c3e-12d5-4f57-9c6c-123456789abc"
DOCUMENT_ID = "11111111-2222-3333-4444-555555555555"
REQUEST = PdfRequest(archivo_base64="JVBERi0xLjQK", nombre="contrato.pdf")
EXTRACTION = ExtractionResult(
    nombre="contrato.pdf",
    texto="Texto",
    checksum="abc123",
    tamano_bytes=128,
    paginas=2,
)
DOCUMENT_BODY = {
    "id": DOCUMENT_ID,
    "nombre": "contrato.pdf",
    "checksum": "abc123",
    "texto": "Texto",
    "tamano_bytes": 128,
    "paginas": 2,
    "created_at": "2026-09-14T18:00:00Z",
    "updated_at": "2026-09-14T18:00:00Z",
}
DOCUMENT = PdfDocument(
    id=UUID(DOCUMENT_ID),
    nombre="contrato.pdf",
    checksum="abc123",
    texto="Texto",
    tamano_bytes=128,
    paginas=2,
    created_at=datetime(2026, 9, 14, 18, 0, tzinfo=UTC),
    updated_at=datetime(2026, 9, 14, 18, 0, tzinfo=UTC),
)


class Recorder:
    """Transporte de prueba: guarda cada request y responde lo configurado."""

    def __init__(self, *responses: httpx.Response) -> None:
        self.requests: list[httpx.Request] = []
        self._responses = list(responses)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return (
            self._responses.pop(0) if len(self._responses) > 1 else self._responses[0]
        )

    def http(self, retry_attempts: int = 0) -> JsonHttpClient:
        return JsonHttpClient(
            httpx.AsyncClient(transport=httpx.MockTransport(self)),
            base_url="http://dependencia:8000",
            service_name="dependencia",
            retry_attempts=retry_attempts,
            retry_delay_seconds=0,
        )

    def body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)


async def test_validation_posts_the_pdf_request() -> None:
    recorder = Recorder(
        httpx.Response(200, json={"valido": True, "nombre": "a", "tamano_bytes": 1})
    )

    await ValidationHttpClient(recorder.http()).validate(REQUEST, CORRELATION_ID)

    assert recorder.requests[0].url.path == "/validar"
    assert recorder.body() == {
        "archivo_base64": "JVBERi0xLjQK",
        "nombre": "contrato.pdf",
    }
    assert recorder.requests[0].headers["X-Correlation-ID"] == CORRELATION_ID


async def test_extraction_returns_the_extraction_result() -> None:
    recorder = Recorder(
        httpx.Response(
            200,
            json={
                "nombre": "contrato.pdf",
                "texto": "Texto",
                "checksum": "abc123",
                "tamano_bytes": 128,
                "paginas": 2,
            },
        )
    )

    result = await ExtractionHttpClient(recorder.http()).extract(
        REQUEST, CORRELATION_ID
    )

    assert recorder.requests[0].url.path == "/extraer"
    assert result == EXTRACTION


async def test_extraction_rejects_a_response_outside_the_contract() -> None:
    recorder = Recorder(httpx.Response(200, json={"text": "formato viejo"}))

    with pytest.raises(DependencyUnavailableError):
        await ExtractionHttpClient(recorder.http()).extract(REQUEST, CORRELATION_ID)


async def test_persistence_create_posts_the_document_fields() -> None:
    recorder = Recorder(httpx.Response(201, json=DOCUMENT_BODY))

    document = await PersistenceUpdatesHttpClient(recorder.http()).create(
        EXTRACTION, CORRELATION_ID
    )

    assert recorder.requests[0].method == "POST"
    assert recorder.requests[0].url.path == "/pdf"
    assert recorder.body() == {
        "nombre": "contrato.pdf",
        "checksum": "abc123",
        "texto": "Texto",
        "tamano_bytes": 128,
        "paginas": 2,
    }
    assert document == DOCUMENT


async def test_persistence_create_is_not_retried() -> None:
    recorder = Recorder(httpx.Response(503, text="no disponible"))

    with pytest.raises(DependencyUnavailableError):
        await PersistenceUpdatesHttpClient(recorder.http(retry_attempts=2)).create(
            EXTRACTION, CORRELATION_ID
        )

    assert len(recorder.requests) == 1


@pytest.mark.parametrize("status", [204, 404])
async def test_persistence_delete_is_idempotent(status: int) -> None:
    recorder = Recorder(httpx.Response(status))

    await PersistenceUpdatesHttpClient(recorder.http()).delete(
        UUID(DOCUMENT_ID), CORRELATION_ID
    )

    assert recorder.requests[0].method == "DELETE"
    assert recorder.requests[0].url.path == f"/pdf/{DOCUMENT_ID}"


async def test_queries_find_a_document_by_checksum() -> None:
    recorder = Recorder(httpx.Response(200, json=DOCUMENT_BODY))

    document = await PersistenceQueriesHttpClient(recorder.http()).find_by_checksum(
        "abc123", CORRELATION_ID
    )

    assert recorder.requests[0].url.path == "/pdf/checksum/abc123"
    assert document == DOCUMENT


async def test_queries_return_none_when_the_checksum_does_not_exist() -> None:
    recorder = Recorder(httpx.Response(404, json={"error": {"code": "X"}}))

    document = await PersistenceQueriesHttpClient(recorder.http()).find_by_checksum(
        "abc123", CORRELATION_ID
    )

    assert document is None


async def test_documents_with_dates_outside_utc_are_rejected() -> None:
    body = DOCUMENT_BODY | {"created_at": "2026-09-14T18:00:00+01:00"}
    recorder = Recorder(httpx.Response(200, json=body))

    with pytest.raises(DependencyUnavailableError):
        await PersistenceQueriesHttpClient(recorder.http()).find_by_checksum(
            "abc123", CORRELATION_ID
        )


async def test_extraction_reads_the_extraction_time_header() -> None:
    body = {
        "nombre": "contrato.pdf",
        "texto": "Texto",
        "checksum": "abc123",
        "tamano_bytes": 128,
        "paginas": 2,
    }
    recorder = Recorder(
        httpx.Response(200, json=body, headers={"X-Extraction-Time-Ms": "12.5"})
    )

    result = await ExtractionHttpClient(recorder.http()).extract(
        REQUEST, CORRELATION_ID
    )

    assert result.extraction_time_ms == 12.5


async def test_extraction_time_is_none_when_the_header_is_missing() -> None:
    body = {
        "nombre": "contrato.pdf",
        "texto": "Texto",
        "checksum": "abc123",
        "tamano_bytes": 128,
        "paginas": 2,
    }
    recorder = Recorder(httpx.Response(200, json=body))

    result = await ExtractionHttpClient(recorder.http()).extract(
        REQUEST, CORRELATION_ID
    )

    assert result.extraction_time_ms is None


async def test_persistence_create_does_not_send_the_extraction_time() -> None:
    # persistencia-actualizaciones rechaza campos extra con 400 (su contrato, A5).
    recorder = Recorder(httpx.Response(201, json=DOCUMENT_BODY))

    await PersistenceUpdatesHttpClient(recorder.http()).create(
        replace(EXTRACTION, extraction_time_ms=12.5), CORRELATION_ID
    )

    assert set(recorder.body()) == {
        "nombre",
        "checksum",
        "texto",
        "tamano_bytes",
        "paginas",
    }
