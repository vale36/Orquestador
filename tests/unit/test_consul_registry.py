"""Contrato 1.6.0: el orquestador se registra en Consul con los tags de Traefik, así
Traefik lo publica por el proveedor Consul Catalog y no por labels del compose."""

import asyncio
import json
from pathlib import Path

import httpx

from app.core.config import Settings
from app.core.consul_registry import ConsulRegistry

TAGS = [
    "traefik.enable=true",
    "traefik.http.routers.orquestador.rule=Host(`pdf.test`)",
]


def settings(tmp_path: Path) -> Settings:
    token = tmp_path / "consul.token"
    token.write_text("test-token", encoding="utf-8")
    return Settings(
        _env_file=None,
        consul_enabled=True,
        consul_http_addr="http://consul:8500",
        consul_http_token_file=token,
        consul_service_address="orquestador",
        consul_service_port=8000,
        consul_service_tags=TAGS,
        request_timeout_seconds=10,
        retry_attempts=2,
        retry_delay_seconds=0.5,
    )


def test_registra_y_deregistra_al_orquestador_con_sus_tags(tmp_path: Path):
    requests = []

    async def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    registry = ConsulRegistry(
        settings=settings(tmp_path),
        instance_id="orquestador-instancia-a",
        transport=httpx.MockTransport(responder),
    )

    asyncio.run(registry.register())
    asyncio.run(registry.deregister())

    assert requests[0].method == "PUT"
    assert str(requests[0].url) == "http://consul:8500/v1/agent/service/register"
    assert requests[0].headers["X-Consul-Token"] == "test-token"
    payload = json.loads(requests[0].content)
    assert payload["ID"] == "orquestador-instancia-a"
    assert payload["Name"] == "orquestador"
    assert payload["Address"] == "orquestador"
    assert payload["Port"] == 8000
    assert payload["Tags"] == TAGS
    assert payload["Checks"][0]["HTTP"] == "http://orquestador:8000/health"
    assert str(requests[1].url).endswith(
        "/v1/agent/service/deregister/orquestador-instancia-a"
    )
