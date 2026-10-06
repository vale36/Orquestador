import asyncio
import json
from typing import Any
from uuid import UUID

import pytest

from app.main import app
from app.schemas.pdf_schemas import (
    PdfDocumentResponseSchema,
    PdfRequestSchema,
    ServiceErrorSchema,
)
from app.services.ports import (
    DependencyUnavailableError,
    ExternalServiceError,
    ExtractionServiceError,
    PersistenceServiceError,
    ValidationServiceError,
)

CORRELATION_ID = "8f6f7c3e-12d5-4f57-9c6c-123456789abc"
REQUEST_BODY = {
    "archivo_base64": "JVBERi0xLjQK...",
    "nombre": "contrato.pdf",
}
DOCUMENT_BODY = {
    "id": CORRELATION_ID,
    "nombre": "contrato.pdf",
    "checksum": "sha256",
    "texto": "Contenido extraído",
    "tamano_bytes": 128,
    "paginas": 2,
    "created_at": "2026-09-14T18:00:00Z",
    "updated_at": "2026-09-14T18:00:00Z",
}


class FakeOrchestratorService:
    def __init__(
        self,
        result: PdfDocumentResponseSchema | Exception | None = None,
    ) -> None:
        self.calls: list[tuple[PdfRequestSchema, str]] = []
        self.result = (
            result
            if result is not None
            else PdfDocumentResponseSchema.model_validate(DOCUMENT_BODY)
        )

    def orchestrate(
        self,
        request: PdfRequestSchema,
        correlation_id: str,
    ) -> PdfDocumentResponseSchema:
        self.calls.append((request, correlation_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def service_error(code: str, message: str) -> ServiceErrorSchema:
    return ServiceErrorSchema(
        code=code,
        message=message,
        details={"source": "test"},
        correlation_id=UUID(CORRELATION_ID),
    )


def invoke_asgi(
    method: str,
    path: str,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    request_body = json.dumps(body).encode()
    messages: list[dict[str, Any]] = []
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {
            "type": "http.request",
            "body": request_body,
            "more_body": False,
        }

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    header_items = {"content-type": "application/json", **(headers or {})}.items()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (name.lower().encode(), value.encode()) for name, value in header_items
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))

    response_start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return (
        response_start["status"],
        {
            name.decode().lower(): value.decode()
            for name, value in response_start["headers"]
        },
        json.loads(response_body),
    )


def test_post_pdf_invokes_orchestrator_and_returns_created_document(
    monkeypatch,
) -> None:
    from app.controllers.pdf_routes import get_orchestrator_service

    service = FakeOrchestratorService()
    monkeypatch.setitem(
        app.dependency_overrides,
        get_orchestrator_service,
        lambda: service,
    )

    status, headers, response_body = invoke_asgi(
        "POST",
        "/pdf",
        REQUEST_BODY,
        {"X-Correlation-ID": CORRELATION_ID},
    )

    assert status == 201, response_body
    assert headers["x-correlation-id"] == CORRELATION_ID
    assert response_body == DOCUMENT_BODY
    assert service.calls == [
        (
            PdfRequestSchema.model_validate(REQUEST_BODY),
            CORRELATION_ID,
        )
    ]


def test_get_health_reports_service_available() -> None:
    status, _, response_body = invoke_asgi("GET", "/health", {})

    assert status == 200
    assert response_body == {"status": "ok"}


def test_post_pdf_generates_correlation_id_when_header_is_missing(monkeypatch) -> None:
    from app.controllers.pdf_routes import get_orchestrator_service

    service = FakeOrchestratorService()
    monkeypatch.setitem(
        app.dependency_overrides,
        get_orchestrator_service,
        lambda: service,
    )

    status, headers, response_body = invoke_asgi("POST", "/pdf", REQUEST_BODY)

    assert status == 201
    correlation_id = headers["x-correlation-id"]
    UUID(correlation_id)
    assert response_body == DOCUMENT_BODY
    assert service.calls[0][1] == correlation_id


def test_post_pdf_returns_common_error_for_invalid_request(monkeypatch) -> None:
    from app.controllers.pdf_routes import get_orchestrator_service

    service = FakeOrchestratorService()
    monkeypatch.setitem(
        app.dependency_overrides,
        get_orchestrator_service,
        lambda: service,
    )
    invalid_request = {"archivo_base64": REQUEST_BODY["archivo_base64"]}

    response_status, headers, response_body = invoke_asgi(
        "POST",
        "/pdf",
        invalid_request,
        {"X-Correlation-ID": CORRELATION_ID},
    )

    assert response_status == 422
    assert headers["x-correlation-id"] == CORRELATION_ID
    assert response_body["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert response_body["error"]["correlation_id"] == CORRELATION_ID
    assert service.calls == []
    assert REQUEST_BODY["archivo_base64"] not in json.dumps(response_body)


def test_invalid_request_without_correlation_id_returns_generated_id(
    monkeypatch,
) -> None:
    from app.controllers.pdf_routes import get_orchestrator_service

    service = FakeOrchestratorService()
    monkeypatch.setitem(
        app.dependency_overrides,
        get_orchestrator_service,
        lambda: service,
    )

    response_status, headers, response_body = invoke_asgi(
        "POST",
        "/pdf",
        {"archivo_base64": REQUEST_BODY["archivo_base64"]},
    )

    correlation_id = headers["x-correlation-id"]
    UUID(correlation_id)
    assert response_status == 422
    assert response_body["error"]["code"] == "REQUEST_VALIDATION_ERROR"
    assert response_body["error"]["correlation_id"] == correlation_id
    assert service.calls == []


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (
            ValidationServiceError(service_error("PDF_INVALID", "invalid PDF")),
            422,
        ),
        (
            ExtractionServiceError(
                service_error("EXTRACTION_FAILED", "extraction failed")
            ),
            502,
        ),
        (
            PersistenceServiceError(
                service_error("PERSISTENCE_FAILED", "persistence failed")
            ),
            502,
        ),
        (
            DependencyUnavailableError(
                service_error("DEPENDENCY_UNAVAILABLE", "service unavailable")
            ),
            503,
        ),
    ],
)
def test_post_pdf_transforms_orchestrator_errors_to_common_response(
    monkeypatch,
    error: ExternalServiceError,
    expected_status: int,
) -> None:
    from app.controllers.pdf_routes import get_orchestrator_service

    service = FakeOrchestratorService(result=error)
    monkeypatch.setitem(
        app.dependency_overrides,
        get_orchestrator_service,
        lambda: service,
    )

    response_status, headers, response_body = invoke_asgi(
        "POST",
        "/pdf",
        REQUEST_BODY,
        {"X-Correlation-ID": CORRELATION_ID},
    )

    assert response_status == expected_status
    assert headers["x-correlation-id"] == CORRELATION_ID
    assert response_body == {"error": error.error.model_dump(mode="json")}
    assert len(service.calls) == 1
