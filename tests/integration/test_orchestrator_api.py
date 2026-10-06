import json
from uuid import UUID

import httpx
import pytest

from app.core.composition import build_orchestrator, get_orchestrator_service
from app.core.config import Settings
from app.core.exceptions import DependencyUnavailableError, ExternalServiceError
from app.main import app
from tests.doubles import CORRELATION_ID, DOCUMENT_ID

REQUEST_BODY = {"archivo_base64": "JVBERi0xLjQK...", "nombre": "contrato.pdf"}
DOCUMENT_BODY = {
    "id": str(DOCUMENT_ID),
    "nombre": "contrato-extraido.pdf",
    "checksum": "sha256-extraido",
    "texto": "Texto extraído del documento",
    "tamano_bytes": 245760,
    "paginas": 3,
    "created_at": "2026-09-14T18:00:00Z",
    "updated_at": "2026-09-14T18:00:00Z",
}


async def test_post_pdf_returns_the_created_document(client) -> None:
    response = await client.post(
        "/pdf", json=REQUEST_BODY, headers={"X-Correlation-ID": CORRELATION_ID}
    )

    assert response.status_code == 201
    assert response.json() == DOCUMENT_BODY
    assert response.headers["X-Correlation-ID"] == CORRELATION_ID


async def test_post_pdf_forwards_the_correlation_id(client, ports) -> None:
    await client.post(
        "/pdf", json=REQUEST_BODY, headers={"X-Correlation-ID": CORRELATION_ID}
    )

    assert ports.validation.calls[0][1] == CORRELATION_ID
    assert ports.extraction.calls[0][1] == CORRELATION_ID
    assert ports.updates.create_calls[0][1] == CORRELATION_ID


async def test_post_pdf_generates_a_correlation_id_when_missing(client) -> None:
    response = await client.post("/pdf", json=REQUEST_BODY)

    UUID(response.headers["X-Correlation-ID"])


@pytest.mark.parametrize(
    "body",
    [{"archivo_base64": "JVBERi0xLjQK..."}, {"nombre": "contrato.pdf"}],
    ids=["sin-nombre", "sin-archivo"],
)
async def test_invalid_request_returns_validation_error(client, ports, body) -> None:
    response = await client.post(
        "/pdf", json=body, headers={"X-Correlation-ID": CORRELATION_ID}
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["correlation_id"] == CORRELATION_ID
    assert ports.validation.calls == []
    assert REQUEST_BODY["archivo_base64"] not in response.text


@pytest.mark.parametrize(
    ("puerto", "code", "status"),
    [
        ("validation", "PDF_INVALID", 422),
        ("validation", "PDF_TOO_LARGE", 413),
        ("extraction", "PDF_CORRUPTED", 422),
        ("updates", "DUPLICATE_CHECKSUM", 409),
        ("updates", "DATABASE_ERROR", 503),
        ("extraction", "INTERNAL_ERROR", 500),
    ],
)
async def test_dependency_errors_keep_the_contract_status(
    client, ports, puerto, code, status
) -> None:
    getattr(ports, puerto).error = ExternalServiceError(code, f"falla {code}")

    response = await client.post(
        "/pdf", json=REQUEST_BODY, headers={"X-Correlation-ID": CORRELATION_ID}
    )

    assert response.status_code == status
    assert response.json() == {
        "error": {
            "code": code,
            "message": f"falla {code}",
            "details": {},
            "correlation_id": CORRELATION_ID,
        }
    }
    assert response.headers["X-Correlation-ID"] == CORRELATION_ID


async def test_unavailable_dependency_returns_503(client, ports) -> None:
    ports.extraction.error = DependencyUnavailableError("extraccion-texto no responde")

    response = await client.post("/pdf", json=REQUEST_BODY)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


async def test_health_is_available(client) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_full_flow_through_the_real_http_adapters(monkeypatch) -> None:
    """La app con los adaptadores reales; solo el transporte HTTP es de prueba."""
    monkeypatch.setenv("RETRY_ATTEMPTS", "1")
    paths: list[str] = []
    extraction_attempts = iter(
        [
            httpx.Response(503, text="arrancando"),
            httpx.Response(
                200,
                json={k: DOCUMENT_BODY[k] for k in ("nombre", "texto", "checksum")}
                | {"tamano_bytes": 245760, "paginas": 3},
            ),
        ]
    )

    def dependencies(request: httpx.Request) -> httpx.Response:
        paths.append(f"{request.url.host}{request.url.path}")
        assert request.headers["X-Correlation-ID"] == CORRELATION_ID
        if request.url.path == "/validar":
            return httpx.Response(200, json={"valido": True})
        if request.url.path == "/extraer":
            return next(extraction_attempts)
        assert json.loads(request.content)["checksum"] == "sha256-extraido"
        return httpx.Response(201, json=DOCUMENT_BODY)

    async with httpx.AsyncClient(transport=httpx.MockTransport(dependencies)) as http:
        service = build_orchestrator(Settings(), http)
        app.dependency_overrides[get_orchestrator_service] = lambda: service
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.post(
                "/pdf", json=REQUEST_BODY, headers={"X-Correlation-ID": CORRELATION_ID}
            )
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json() == DOCUMENT_BODY
    assert paths == [
        "validacion.test/validar",
        "extraccion.test/extraer",
        "extraccion.test/extraer",
        "actualizaciones.test/pdf",
    ]
