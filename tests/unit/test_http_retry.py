import json
from io import BytesIO
from urllib.error import HTTPError
from uuid import UUID

import pytest

from app.clients.persistence_updates_client import PersistenceUpdatesHttpClient
from app.schemas.pdf_schemas import PersistenceCreateRequestSchema
from app.services.ports import (
    DependencyUnavailableError,
    PersistenceServiceError,
)

CORRELATION_ID = "8f6f7c3e-12d5-4f57-9c6c-123456789abc"
REQUEST = PersistenceCreateRequestSchema(
    nombre="contrato.pdf",
    checksum="sha256",
    texto="Contenido extraído",
    tamano_bytes=128,
    paginas=2,
)
CREATED_DOCUMENT = {
    "id": CORRELATION_ID,
    **REQUEST.model_dump(),
    "created_at": "2026-09-14T18:00:00Z",
    "updated_at": "2026-09-14T18:00:00Z",
}
TRANSIENT_ERROR = {
    "error": {
        "code": "DEPENDENCY_UNAVAILABLE",
        "message": "Servicio temporalmente no disponible",
        "details": {},
        "correlation_id": CORRELATION_ID,
    }
}
DEFINITIVE_ERROR = {
    "error": {
        "code": "DUPLICATE_CHECKSUM",
        "message": "El checksum ya existe",
        "details": {},
        "correlation_id": CORRELATION_ID,
    }
}


class FakeResponse(BytesIO):
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def configure_environment(monkeypatch, attempts: str = "2", delay: str = "0.01"):
    monkeypatch.setenv(
        "PERSISTENCIA_ACTUALIZACIONES_URL",
        "http://persistence.test",
    )
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "1.25")
    monkeypatch.setenv("RETRY_ATTEMPTS", attempts)
    monkeypatch.setenv("RETRY_DELAY_SECONDS", delay)


def http_error(status: int, payload: dict) -> HTTPError:
    return HTTPError(
        "http://persistence.test/pdf",
        status,
        "dependency error",
        None,
        BytesIO(json.dumps(payload).encode("utf-8")),
    )


def test_timeout_uses_configured_limit_and_is_translated(monkeypatch) -> None:
    configure_environment(monkeypatch, attempts="0")
    calls = []

    def timeout(request, timeout):
        calls.append((request.get_header("X-correlation-id"), timeout))
        raise TimeoutError("request timed out")

    monkeypatch.setattr("urllib.request.urlopen", timeout)
    monkeypatch.setattr("time.sleep", lambda _: None, raising=False)

    with pytest.raises(DependencyUnavailableError):
        PersistenceUpdatesHttpClient().create(REQUEST, CORRELATION_ID)

    assert calls == [(CORRELATION_ID, 1.25)]


def test_retries_timeout_exactly_as_configured_and_then_succeeds(
    monkeypatch,
    caplog,
) -> None:
    configure_environment(monkeypatch, attempts="2", delay="0")
    calls = []
    sleeps = []

    def timeout_then_success(request, timeout):
        calls.append(request.get_header("X-correlation-id"))
        if len(calls) < 3:
            raise TimeoutError("request timed out")
        return FakeResponse(json.dumps(CREATED_DOCUMENT).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", timeout_then_success)
    monkeypatch.setattr("time.sleep", sleeps.append, raising=False)

    result = PersistenceUpdatesHttpClient().create(REQUEST, CORRELATION_ID)

    assert str(result.id) == CORRELATION_ID
    assert result.nombre == "contrato.pdf"
    assert calls == [CORRELATION_ID] * 3
    assert sleeps == []
    assert caplog.text.count("Retrying external request") == 2
    assert "reason=timeout" in caplog.text
    assert "JVBERi0xLjQK" not in caplog.text


def test_retry_exhaustion_is_finite_and_propagates_dependency_error(
    monkeypatch,
) -> None:
    configure_environment(monkeypatch, attempts="3", delay="0")
    calls = []

    def always_timeout(request, timeout):
        calls.append(request.get_header("X-correlation-id"))
        raise TimeoutError("request timed out")

    monkeypatch.setattr("urllib.request.urlopen", always_timeout)
    monkeypatch.setattr("time.sleep", lambda _: None, raising=False)

    with pytest.raises(DependencyUnavailableError) as error:
        PersistenceUpdatesHttpClient().create(REQUEST, CORRELATION_ID)

    assert len(calls) == 4
    assert error.value.error.correlation_id == UUID(CORRELATION_ID)


def test_definitive_http_error_is_not_retried(monkeypatch) -> None:
    configure_environment(monkeypatch, attempts="5", delay="0")
    calls = []

    def definitive_error(request, timeout):
        calls.append(request.get_header("X-correlation-id"))
        raise http_error(409, DEFINITIVE_ERROR)

    monkeypatch.setattr("urllib.request.urlopen", definitive_error)
    monkeypatch.setattr("time.sleep", lambda _: None, raising=False)

    with pytest.raises(PersistenceServiceError) as error:
        PersistenceUpdatesHttpClient().create(REQUEST, CORRELATION_ID)

    assert len(calls) == 1
    assert error.value.error.code == "DUPLICATE_CHECKSUM"


def test_transient_http_error_is_retried(monkeypatch) -> None:
    configure_environment(monkeypatch, attempts="1", delay="0")
    calls = []

    def unavailable_then_success(request, timeout):
        calls.append(request.get_header("X-correlation-id"))
        if len(calls) == 1:
            raise http_error(503, TRANSIENT_ERROR)
        return FakeResponse(json.dumps(CREATED_DOCUMENT).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", unavailable_then_success)
    monkeypatch.setattr("time.sleep", lambda _: None, raising=False)

    result = PersistenceUpdatesHttpClient().create(REQUEST, CORRELATION_ID)

    assert result.nombre == "contrato.pdf"
    assert calls == [CORRELATION_ID, CORRELATION_ID]


def test_retry_delay_is_used_between_attempts(monkeypatch) -> None:
    configure_environment(monkeypatch, attempts="2", delay="0.125")
    sleeps = []

    def always_timeout(request, timeout):
        raise TimeoutError("request timed out")

    monkeypatch.setattr("urllib.request.urlopen", always_timeout)
    monkeypatch.setattr("time.sleep", sleeps.append, raising=False)

    with pytest.raises(DependencyUnavailableError):
        PersistenceUpdatesHttpClient().create(REQUEST, CORRELATION_ID)

    assert sleeps == [0.125, 0.125]


def test_connection_error_uses_same_bounded_retry_policy(monkeypatch) -> None:
    configure_environment(monkeypatch, attempts="2", delay="0")
    calls = []

    def connection_error(request, timeout):
        calls.append(request.get_header("X-correlation-id"))
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", connection_error)
    monkeypatch.setattr("time.sleep", lambda _: None, raising=False)

    with pytest.raises(DependencyUnavailableError):
        PersistenceUpdatesHttpClient().create(REQUEST, CORRELATION_ID)

    assert calls == [CORRELATION_ID] * 3


@pytest.mark.parametrize("attempts", ["-1", "1.5", "inf", ""])
def test_retry_attempts_must_be_a_non_negative_integer(
    monkeypatch,
    attempts: str,
) -> None:
    configure_environment(monkeypatch, attempts=attempts)

    with pytest.raises(ValueError, match="RETRY_ATTEMPTS"):
        PersistenceUpdatesHttpClient()
