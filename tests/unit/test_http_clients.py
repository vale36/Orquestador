import json
from io import BytesIO
from urllib.error import HTTPError, URLError
from uuid import UUID

import pytest

from app.clients.extraction_client import ExtractionHttpClient
from app.clients.persistence_updates_client import PersistenceUpdatesHttpClient
from app.clients.validation_client import ValidationHttpClient
from app.schemas.pdf_schemas import (
    ExtractionResponseSchema,
    PdfDocumentResponseSchema,
    PdfRequestSchema,
    PersistenceCreateRequestSchema,
    ValidationSuccessSchema,
)
from app.services.ports import (
    DependencyUnavailableError,
    ExtractionPort,
    ExtractionServiceError,
    PersistenceServiceError,
    ValidationPort,
    ValidationServiceError,
)

CORRELATION_ID = "8f6f7c3e-12d5-4f57-9c6c-123456789abc"
PDF_REQUEST = PdfRequestSchema(
    archivo_base64="JVBERi0xLjQK...",
    nombre="contrato.pdf",
)
EXTRACTION_RESPONSE = {
    "nombre": "contrato.pdf",
    "texto": "Contenido extraído",
    "checksum": "sha256",
    "tamano_bytes": 128,
    "paginas": 2,
}
PERSISTENCE_REQUEST = PersistenceCreateRequestSchema(**EXTRACTION_RESPONSE)
DOCUMENT_RESPONSE = {
    "id": CORRELATION_ID,
    **EXTRACTION_RESPONSE,
    "created_at": "2026-09-14T18:00:00Z",
    "updated_at": "2026-09-14T18:00:00Z",
}
REMOTE_ERROR = {
    "error": {
        "code": "PDF_INVALID",
        "message": "El archivo no es un PDF válido",
        "details": {},
        "correlation_id": CORRELATION_ID,
    }
}


class FakeResponse(BytesIO):
    status = 200

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def install_response(monkeypatch, payload: object, status: int = 200) -> list:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        response = FakeResponse(json.dumps(payload).encode("utf-8"))
        response.status = status
        return response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return calls


def install_http_error(monkeypatch, payload: object, status: int = 422) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            status,
            "dependency error",
            None,
            BytesIO(json.dumps(payload).encode("utf-8")),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)


def assert_request(call, expected_url: str, expected_payload: dict) -> None:
    request, timeout = call
    assert request.full_url == expected_url
    assert request.get_method() == "POST"
    assert json.loads(request.data) == expected_payload
    assert request.get_header("X-correlation-id") == CORRELATION_ID
    assert request.get_header("Content-type") == "application/json"
    assert timeout == 2.5


def configure_urls(monkeypatch) -> None:
    monkeypatch.setenv("VALIDACION_URL", "http://validation.test")
    monkeypatch.setenv("EXTRACCION_URL", "http://extraction.test")
    monkeypatch.setenv(
        "PERSISTENCIA_ACTUALIZACIONES_URL", "http://persistence.test"
    )
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("RETRY_ATTEMPTS", "0")
    monkeypatch.setenv("RETRY_DELAY_SECONDS", "0")


def test_validation_client_sends_configured_json_and_correlation_id(monkeypatch) -> None:
    configure_urls(monkeypatch)
    calls = install_response(
        monkeypatch,
        {"valido": True, "nombre": "contrato.pdf", "tamano_bytes": 128},
    )

    result = ValidationHttpClient().validate(PDF_REQUEST, CORRELATION_ID)

    assert isinstance(result, ValidationSuccessSchema)
    assert result.valido is True
    assert_request(
        calls[0],
        "http://validation.test/validar",
        PDF_REQUEST.model_dump(),
    )


def test_validation_client_translates_contract_http_error(monkeypatch) -> None:
    configure_urls(monkeypatch)
    install_http_error(monkeypatch, REMOTE_ERROR)

    with pytest.raises(ValidationServiceError) as error:
        ValidationHttpClient().validate(PDF_REQUEST, CORRELATION_ID)

    assert error.value.error.code == "PDF_INVALID"
    assert error.value.error.correlation_id == UUID(CORRELATION_ID)


def test_validation_client_translates_connection_error(monkeypatch) -> None:
    configure_urls(monkeypatch)

    def fail_connection(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fail_connection)

    with pytest.raises(DependencyUnavailableError) as error:
        ValidationHttpClient().validate(PDF_REQUEST, CORRELATION_ID)

    assert error.value.error.correlation_id == UUID(CORRELATION_ID)


def test_extraction_client_sends_configured_json_and_correlation_id(monkeypatch) -> None:
    configure_urls(monkeypatch)
    calls = install_response(monkeypatch, EXTRACTION_RESPONSE)

    result = ExtractionHttpClient().extract(PDF_REQUEST, CORRELATION_ID)

    assert isinstance(result, ExtractionResponseSchema)
    assert result.checksum == "sha256"
    assert_request(
        calls[0],
        "http://extraction.test/extraer",
        PDF_REQUEST.model_dump(),
    )


def test_extraction_client_translates_contract_http_error(monkeypatch) -> None:
    configure_urls(monkeypatch)
    install_http_error(monkeypatch, REMOTE_ERROR)

    with pytest.raises(ExtractionServiceError) as error:
        ExtractionHttpClient().extract(PDF_REQUEST, CORRELATION_ID)

    assert error.value.error.code == "PDF_INVALID"
    assert error.value.error.correlation_id == UUID(CORRELATION_ID)


def test_extraction_client_translates_connection_error(monkeypatch) -> None:
    configure_urls(monkeypatch)

    def fail_connection(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fail_connection)

    with pytest.raises(DependencyUnavailableError) as error:
        ExtractionHttpClient().extract(PDF_REQUEST, CORRELATION_ID)

    assert error.value.error.correlation_id == UUID(CORRELATION_ID)


def test_persistence_client_sends_create_request_and_correlation_id(monkeypatch) -> None:
    configure_urls(monkeypatch)
    calls = install_response(monkeypatch, DOCUMENT_RESPONSE)

    result = PersistenceUpdatesHttpClient().create(
        PERSISTENCE_REQUEST, CORRELATION_ID
    )

    assert isinstance(result, PdfDocumentResponseSchema)
    assert result.id == UUID(CORRELATION_ID)
    assert_request(
        calls[0],
        "http://persistence.test/pdf",
        PERSISTENCE_REQUEST.model_dump(),
    )


def test_persistence_client_translates_contract_http_error(monkeypatch) -> None:
    configure_urls(monkeypatch)
    install_http_error(monkeypatch, REMOTE_ERROR)

    with pytest.raises(PersistenceServiceError) as error:
        PersistenceUpdatesHttpClient().create(
            PERSISTENCE_REQUEST, CORRELATION_ID
        )

    assert error.value.error.code == "PDF_INVALID"
    assert error.value.error.correlation_id == UUID(CORRELATION_ID)


def test_persistence_client_translates_connection_error(monkeypatch) -> None:
    configure_urls(monkeypatch)

    def fail_connection(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fail_connection)

    with pytest.raises(DependencyUnavailableError) as error:
        PersistenceUpdatesHttpClient().create(
            PERSISTENCE_REQUEST, CORRELATION_ID
        )

    assert error.value.error.correlation_id == UUID(CORRELATION_ID)


def test_persistence_client_translates_transport_timeout(monkeypatch) -> None:
    configure_urls(monkeypatch)

    def timeout(request, timeout):
        raise TimeoutError("request timed out")

    monkeypatch.setattr("urllib.request.urlopen", timeout)

    with pytest.raises(DependencyUnavailableError) as error:
        PersistenceUpdatesHttpClient().create(
            PERSISTENCE_REQUEST, CORRELATION_ID
        )

    assert error.value.error.code == "DEPENDENCY_UNAVAILABLE"
    assert error.value.error.correlation_id == UUID(CORRELATION_ID)


def test_http_clients_implement_their_available_ports(monkeypatch) -> None:
    configure_urls(monkeypatch)

    assert isinstance(ValidationHttpClient(), ValidationPort)
    assert isinstance(ExtractionHttpClient(), ExtractionPort)
    assert callable(PersistenceUpdatesHttpClient().create)
