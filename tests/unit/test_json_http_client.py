import json

import httpx
import pytest

from app.core.exceptions import DependencyUnavailableError, ExternalServiceError
from app.core.json_http_client import JsonHttpClient

CORRELATION_ID = "8f6f7c3e-12d5-4f57-9c6c-123456789abc"


def error_body(code: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": f"mensaje de {code}",
            "details": {"campo": "valor"},
            "correlation_id": CORRELATION_ID,
        }
    }


def build_client(handler, retry_attempts: int = 0) -> JsonHttpClient:
    transport = httpx.MockTransport(handler)
    return JsonHttpClient(
        httpx.AsyncClient(transport=transport),
        base_url="http://dependencia:8000",
        service_name="dependencia",
        retry_attempts=retry_attempts,
        retry_delay_seconds=0,
    )


async def test_sends_json_and_correlation_id_and_returns_the_body() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    body = await build_client(handler).request(
        "POST", "/extraer", CORRELATION_ID, json={"nombre": "a.pdf"}
    )

    assert body == {"ok": True}
    assert str(requests[0].url) == "http://dependencia:8000/extraer"
    assert requests[0].headers["X-Correlation-ID"] == CORRELATION_ID
    assert json.loads(requests[0].content) == {"nombre": "a.pdf"}


async def test_error_with_the_common_format_keeps_code_message_and_details() -> None:
    client = build_client(lambda _: httpx.Response(409, json=error_body("DUPLICATE")))

    with pytest.raises(ExternalServiceError) as error:
        await client.request("POST", "/pdf", CORRELATION_ID, json={})

    assert error.value.code == "DUPLICATE"
    assert error.value.message == "mensaje de DUPLICATE"
    assert error.value.details == {"campo": "valor"}


async def test_error_without_the_common_format_is_a_dependency_failure() -> None:
    client = build_client(lambda _: httpx.Response(502, text="Bad Gateway"))

    with pytest.raises(DependencyUnavailableError):
        await client.request("POST", "/pdf", CORRELATION_ID, json={})


@pytest.mark.parametrize(
    "transport_error",
    [httpx.ConnectError("sin conexion"), httpx.ReadTimeout("timeout")],
    ids=["conexion", "timeout"],
)
async def test_network_failures_are_dependency_unavailable(transport_error) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise transport_error

    with pytest.raises(DependencyUnavailableError) as error:
        await build_client(handler).request("POST", "/validar", CORRELATION_ID)

    assert error.value.code == "DEPENDENCY_UNAVAILABLE"


async def test_retries_transient_failures_until_success() -> None:
    responses = iter(
        [
            httpx.Response(503, json=error_body("DATABASE_ERROR")),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    body = await build_client(lambda _: next(responses), retry_attempts=1).request(
        "POST", "/validar", CORRELATION_ID
    )

    assert body == {"ok": True}


async def test_retry_exhaustion_is_finite_and_keeps_the_last_error() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503, json=error_body("DATABASE_ERROR"))

    with pytest.raises(ExternalServiceError) as error:
        await build_client(handler, retry_attempts=2).request(
            "POST", "/validar", CORRELATION_ID
        )

    assert len(calls) == 3
    assert error.value.code == "DATABASE_ERROR"


async def test_non_idempotent_requests_are_sent_once() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("timeout")

    with pytest.raises(DependencyUnavailableError):
        await build_client(handler, retry_attempts=2).request(
            "POST", "/pdf", CORRELATION_ID, json={}, retry=False
        )

    assert len(calls) == 1


async def test_not_found_can_be_an_expected_answer() -> None:
    client = build_client(
        lambda _: httpx.Response(404, json=error_body("RESOURCE_NOT_FOUND"))
    )

    body = await client.request(
        "GET", "/pdf/checksum/abc", CORRELATION_ID, not_found_ok=True
    )

    assert body is None


async def test_no_content_returns_none() -> None:
    client = build_client(lambda _: httpx.Response(204))

    assert await client.request("DELETE", "/pdf/1", CORRELATION_ID) is None
