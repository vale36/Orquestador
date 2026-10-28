from pathlib import Path

import httpx

from app.core.composition import build_orchestrator
from app.core.config import Settings
from app.core.exceptions import DependencyUnavailableError
from app.models.pdf_document import PdfRequest
from tests.doubles import CORRELATION_ID


async def test_consul_discovery_resolves_the_service_at_request_time(tmp_path) -> None:
    token_file = tmp_path / "consul.token"
    token_file.write_text("orchestrator-token", encoding="utf-8")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "consul":
            return httpx.Response(
                200,
                json=[
                    {
                        "Node": {"Node": "validation"},
                        "Service": {"Address": "validacion-pdf", "Port": 8000},
                        "Checks": [{"Status": "passing"}],
                    }
                ],
            )
        return httpx.Response(200, json={"valido": True})

    settings = Settings(
        consul_enabled=True,
        consul_http_addr="http://consul:8500",
        consul_http_token_file=token_file,
        request_timeout_seconds=1,
        retry_attempts=0,
        retry_delay_seconds=0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        orchestrator = build_orchestrator(settings, http)
        await orchestrator._validation_service.validate(
            PdfRequest(archivo_base64="JVBERi0xLjQK", nombre="a.pdf"),
            CORRELATION_ID,
        )

    assert [request.url.host for request in requests] == ["consul", "validacion-pdf"]
    assert requests[0].headers["X-Consul-Token"] == "orchestrator-token"


async def test_consul_without_fallback_never_calls_fixed_url(tmp_path) -> None:
    token_file = tmp_path / "consul.token"
    token_file.write_text("orchestrator-token", encoding="utf-8")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    settings = Settings(
        validacion_url="http://validacion-fixed:8000",
        extraccion_url="http://extraccion-fixed:8000",
        persistencia_consultas_url="http://consultas-fixed:8000",
        persistencia_actualizaciones_url="http://actualizaciones-fixed:8000",
        consul_enabled=True,
        consul_http_addr="http://consul:8500",
        consul_http_token_file=token_file,
        consul_fallback_enabled=False,
        request_timeout_seconds=1,
        retry_attempts=0,
        retry_delay_seconds=0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        orchestrator = build_orchestrator(settings, http)
        try:
            await orchestrator._validation_service.validate(
                PdfRequest(archivo_base64="JVBERi0xLjQK", nombre="a.pdf"),
                CORRELATION_ID,
            )
        except DependencyUnavailableError:
            pass
        else:
            raise AssertionError("se esperaba DependencyUnavailableError")

    assert len(requests) == 1
    assert requests[0].url.host == "consul"


async def test_extraction_uses_registered_consul_service_name(tmp_path) -> None:
    token_file = tmp_path / "consul.token"
    token_file.write_text("orchestrator-token", encoding="utf-8")
    requested_services: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "consul":
            requested_services.append(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(
                200,
                json=[
                    {
                        "Node": {"Node": "extraction"},
                        "Service": {"Address": "extraccion", "Port": 8000},
                        "Checks": [{"Status": "passing"}],
                    }
                ],
            )
        return httpx.Response(
            200,
            json={
                "nombre": "a.pdf",
                "paginas": 1,
                "texto": "texto",
                "checksum": "checksum",
                "tamano_bytes": 1,
                "metadata": {},
                "extraccion_tiempo_ms": 1,
            },
        )

    settings = Settings(
        consul_enabled=True,
        consul_http_addr="http://consul:8500",
        consul_http_token_file=token_file,
        request_timeout_seconds=1,
        retry_attempts=0,
        retry_delay_seconds=0,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        orchestrator = build_orchestrator(settings, http)
        await orchestrator._extraction_service.extract(
            PdfRequest(archivo_base64="JVBERi0xLjQK", nombre="a.pdf"),
            CORRELATION_ID,
        )

    assert requested_services == ["extraccion"]


def test_compose_mounts_the_orchestrator_token_as_read_only_secret() -> None:
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(
        encoding="utf-8"
    )

    assert "../dockers/consul/generated/orchestrator.token" in compose
    assert "target: /run/secrets/consul_orchestrator_token" in compose
    assert "mode: 0444" in compose
    assert 'CONSUL_FALLBACK_ENABLED: "false"' in compose
