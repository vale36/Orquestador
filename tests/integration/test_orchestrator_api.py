import asyncio
import json
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any
from urllib.error import HTTPError
from uuid import UUID

from app.main import app
from app.schemas.pdf_schemas import (
    ExtractionResponseSchema,
    PdfDocumentResponseSchema,
    PdfRequestSchema,
    PersistenceCreateRequestSchema,
    ServiceErrorSchema,
    ValidationSuccessSchema,
)
from app.services.orchestrator import OrchestratorService
from app.services.ports import (
    ExtractionPort,
    ExtractionServiceError,
    PersistenceServiceError,
    PersistenceUpdatesPort,
    ValidationPort,
    ValidationServiceError,
)

CORRELATION_ID = "8f6f7c3e-12d5-4f57-9c6c-123456789abc"
REQUEST_BODY = {
    "archivo_base64": "JVBERi0xLjQK...",
    "nombre": "contrato.pdf",
}
DOCUMENT_BODY = {
    "id": CORRELATION_ID,
    "nombre": "contrato-extraido.pdf",
    "checksum": "sha256-extraido",
    "texto": "Contenido extraído",
    "tamano_bytes": 128,
    "paginas": 2,
    "created_at": "2026-09-14T18:00:00Z",
    "updated_at": "2026-09-14T18:00:00Z",
}
CREATED_DOCUMENT = PdfDocumentResponseSchema.model_validate(DOCUMENT_BODY)
EXTRACTION_RESULT = ExtractionResponseSchema(
    nombre="contrato-extraido.pdf",
    texto="Contenido extraído",
    checksum="sha256-extraido",
    tamano_bytes=128,
    paginas=2,
)


class FakeHttpResponse(BytesIO):
    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def service_error(
    code: str,
    message: str,
    correlation_id: str = CORRELATION_ID,
) -> ServiceErrorSchema:
    return ServiceErrorSchema(
        code=code,
        message=message,
        details={},
        correlation_id=UUID(correlation_id),
    )


@dataclass
class FakeValidationPort:
    result: ValidationSuccessSchema | Exception = field(
        default_factory=lambda: ValidationSuccessSchema(
            valido=True,
            nombre="contrato.pdf",
            tamano_bytes=128,
        )
    )
    calls: list[tuple[PdfRequestSchema, str]] = field(default_factory=list)

    def validate(
        self,
        request: PdfRequestSchema,
        correlation_id: str,
    ) -> ValidationSuccessSchema:
        self.calls.append((request, correlation_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class FakeExtractionPort:
    result: ExtractionResponseSchema | Exception = field(
        default_factory=lambda: EXTRACTION_RESULT
    )
    calls: list[tuple[PdfRequestSchema, str]] = field(default_factory=list)

    def extract(
        self,
        request: PdfRequestSchema,
        correlation_id: str,
    ) -> ExtractionResponseSchema:
        self.calls.append((request, correlation_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class FakePersistencePort:
    result: PdfDocumentResponseSchema | Exception = field(
        default_factory=lambda: CREATED_DOCUMENT
    )
    create_calls: list[tuple[PersistenceCreateRequestSchema, str]] = field(
        default_factory=list
    )
    compensation_calls: list[tuple[str, str]] = field(default_factory=list)

    def create(
        self,
        request: PersistenceCreateRequestSchema,
        correlation_id: str,
    ) -> PdfDocumentResponseSchema:
        self.create_calls.append((request, correlation_id))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def compensate(self, checksum: str, correlation_id: str) -> None:
        self.compensation_calls.append((checksum, correlation_id))


def build_orchestrator(
    validation: ValidationPort,
    extraction: ExtractionPort,
    persistence: PersistenceUpdatesPort,
) -> OrchestratorService:
    return OrchestratorService(validation, extraction, persistence)


def invoke_asgi(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    request_body = json.dumps(body or {}).encode()
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

    request_headers = {"content-type": "application/json", **(headers or {})}
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
            (name.lower().encode(), value.encode())
            for name, value in request_headers.items()
        ],
        "client": ("integration-test", 50000),
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


def install_orchestrator(
    monkeypatch,
    validation: ValidationPort,
    extraction: ExtractionPort,
    persistence: PersistenceUpdatesPort,
) -> OrchestratorService:
    from app.services.dependencies import get_orchestrator_service

    orchestrator = build_orchestrator(validation, extraction, persistence)
    monkeypatch.setitem(
        app.dependency_overrides,
        get_orchestrator_service,
        lambda: orchestrator,
    )
    return orchestrator


def configure_http_clients(monkeypatch, retry_attempts: str) -> None:
    monkeypatch.setenv("VALIDACION_URL", "http://validation.test")
    monkeypatch.setenv("EXTRACCION_URL", "http://extraction.test")
    monkeypatch.setenv(
        "PERSISTENCIA_ACTUALIZACIONES_URL",
        "http://persistence.test",
    )
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "0.75")
    monkeypatch.setenv("RETRY_ATTEMPTS", retry_attempts)
    monkeypatch.setenv("RETRY_DELAY_SECONDS", "0")


def test_post_pdf_runs_real_orchestrator_with_controlled_ports(
    monkeypatch,
) -> None:
    validation = FakeValidationPort()
    extraction = FakeExtractionPort()
    persistence = FakePersistencePort()
    install_orchestrator(monkeypatch, validation, extraction, persistence)

    status, response_headers, response_body = invoke_asgi(
        "POST",
        "/pdf",
        REQUEST_BODY,
        {"X-Correlation-ID": CORRELATION_ID},
    )

    assert status == 201
    assert response_headers["x-correlation-id"] == CORRELATION_ID
    assert response_body == DOCUMENT_BODY
    assert validation.calls[0][1] == CORRELATION_ID
    assert extraction.calls[0][1] == CORRELATION_ID
    assert persistence.create_calls[0][1] == CORRELATION_ID
    assert persistence.create_calls[0][0].checksum == EXTRACTION_RESULT.checksum
    assert persistence.compensation_calls == []


def test_validation_error_returns_common_error_and_stops_flow(monkeypatch) -> None:
    validation_error = ValidationServiceError(
        service_error("PDF_INVALID", "invalid PDF")
    )
    validation = FakeValidationPort(result=validation_error)
    extraction = FakeExtractionPort()
    persistence = FakePersistencePort()
    install_orchestrator(monkeypatch, validation, extraction, persistence)

    status, response_headers, response_body = invoke_asgi(
        "POST",
        "/pdf",
        REQUEST_BODY,
        {"X-Correlation-ID": CORRELATION_ID},
    )

    assert status == 422
    assert response_headers["x-correlation-id"] == CORRELATION_ID
    assert response_body == {"error": validation_error.error.model_dump(mode="json")}
    assert len(validation.calls) == 1
    assert extraction.calls == []
    assert persistence.create_calls == []
    assert persistence.compensation_calls == []


def test_extraction_error_returns_common_error_without_persistence(
    monkeypatch,
) -> None:
    extraction_error = ExtractionServiceError(
        service_error("PDF_CORRUPTED", "extraction failed")
    )
    validation = FakeValidationPort()
    extraction = FakeExtractionPort(result=extraction_error)
    persistence = FakePersistencePort()
    install_orchestrator(monkeypatch, validation, extraction, persistence)

    status, response_headers, response_body = invoke_asgi(
        "POST",
        "/pdf",
        REQUEST_BODY,
        {"X-Correlation-ID": CORRELATION_ID},
    )

    assert status == 422
    assert response_headers["x-correlation-id"] == CORRELATION_ID
    assert response_body == {"error": extraction_error.error.model_dump(mode="json")}
    assert len(validation.calls) == 1
    assert len(extraction.calls) == 1
    assert persistence.create_calls == []
    assert persistence.compensation_calls == []


def test_persistence_error_returns_common_error_and_compensates(
    monkeypatch,
) -> None:
    persistence_error = PersistenceServiceError(
        service_error("DATABASE_ERROR", "persistence failed")
    )
    validation = FakeValidationPort()
    extraction = FakeExtractionPort()
    persistence = FakePersistencePort(result=persistence_error)
    install_orchestrator(monkeypatch, validation, extraction, persistence)

    status, response_headers, response_body = invoke_asgi(
        "POST",
        "/pdf",
        REQUEST_BODY,
        {"X-Correlation-ID": CORRELATION_ID},
    )

    assert status == 503
    assert response_headers["x-correlation-id"] == CORRELATION_ID
    assert response_body == {"error": persistence_error.error.model_dump(mode="json")}
    assert len(persistence.create_calls) == 1
    assert persistence.compensation_calls == [
        (EXTRACTION_RESULT.checksum, CORRELATION_ID)
    ]


def test_http_timeout_becomes_common_503_response(monkeypatch) -> None:
    configure_http_clients(monkeypatch, retry_attempts="0")
    calls: list[tuple[str, float, str | None]] = []

    def timeout(request, timeout):
        calls.append(
            (
                request.full_url,
                timeout,
                request.get_header("X-correlation-id"),
            )
        )
        raise TimeoutError("controlled timeout")

    monkeypatch.setattr("urllib.request.urlopen", timeout)

    status, response_headers, response_body = invoke_asgi(
        "POST",
        "/pdf",
        REQUEST_BODY,
        {"X-Correlation-ID": CORRELATION_ID},
    )

    assert status == 503
    assert response_headers["x-correlation-id"] == CORRELATION_ID
    assert response_body["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert response_body["error"]["correlation_id"] == CORRELATION_ID
    assert calls == [
        (
            "http://validation.test/validar",
            0.75,
            CORRELATION_ID,
        )
    ]


def test_http_retry_recovers_and_completes_flow_with_controlled_transport(
    monkeypatch,
    caplog,
) -> None:
    configure_http_clients(monkeypatch, retry_attempts="1")
    calls: list[tuple[str, str | None, float]] = []
    validation_attempts = 0

    def controlled_urlopen(request, timeout):
        nonlocal validation_attempts
        calls.append(
            (
                request.full_url,
                request.get_header("X-correlation-id"),
                timeout,
            )
        )
        if request.full_url.endswith("/validar"):
            validation_attempts += 1
            if validation_attempts == 1:
                error_body = json.dumps(
                    {
                        "error": service_error(
                            "DEPENDENCY_UNAVAILABLE",
                            "temporary validation service error",
                        ).model_dump(mode="json")
                    }
                ).encode()
                raise HTTPError(
                    request.full_url,
                    503,
                    "controlled temporary error",
                    None,
                    BytesIO(error_body),
                )
            response_body: object = {
                "valido": True,
                "nombre": "contrato.pdf",
                "tamano_bytes": 128,
            }
        elif request.full_url.endswith("/extraer"):
            response_body = EXTRACTION_RESULT.model_dump(mode="json")
        else:
            response_body = DOCUMENT_BODY
        return FakeHttpResponse(json.dumps(response_body).encode())

    monkeypatch.setattr("urllib.request.urlopen", controlled_urlopen)
    monkeypatch.setattr("time.sleep", lambda _: None, raising=False)

    status, response_headers, response_body = invoke_asgi(
        "POST",
        "/pdf",
        REQUEST_BODY,
        {"X-Correlation-ID": CORRELATION_ID},
    )

    assert status == 201
    assert response_headers["x-correlation-id"] == CORRELATION_ID
    assert response_body == DOCUMENT_BODY
    assert [call[0].rsplit("/", 1)[-1] for call in calls] == [
        "validar",
        "validar",
        "extraer",
        "pdf",
    ]
    assert validation_attempts == 2
    assert all(call[1] == CORRELATION_ID for call in calls)
    assert all(call[2] == 0.75 for call in calls)
    assert "Retrying external request" in caplog.text


def test_health_is_available_without_external_http_calls(monkeypatch) -> None:
    def unexpected_http_call(*args, **kwargs):
        raise AssertionError("health endpoint must not call external services")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_http_call)

    status, _, response_body = invoke_asgi("GET", "/health")

    assert status == 200
    assert response_body == {"status": "ok"}
