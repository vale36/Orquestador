"""Registro del orquestador en Consul (contrato 1.6.0), igual que los servicios
internos pero con los tags de Traefik."""

import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class ConsulRegistry:
    settings: Settings
    instance_id: str
    transport: httpx.AsyncBaseTransport | None = None

    async def register(self) -> None:
        config = self._validate_config()
        async with self._client(config.token) as client:
            response = await client.put(
                f"{config.address}/v1/agent/service/register",
                json=self._registration_payload(),
            )
            response.raise_for_status()

    async def deregister(self) -> None:
        config = self._validate_config()
        async with self._client(config.token) as client:
            response = await client.put(
                f"{config.address}/v1/agent/service/deregister/{quote(self.instance_id)}"
            )
            response.raise_for_status()

    def _client(self, token: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={"X-Consul-Token": token}, timeout=3, transport=self.transport
        )

    def _validate_config(self) -> "ConsulConfig":
        if not self.settings.consul_enabled:
            raise ValueError("Consul registration is disabled")
        if not self.settings.consul_http_token_file:
            raise ValueError("CONSUL_HTTP_TOKEN_FILE is required")
        token = Path(self.settings.consul_http_token_file).read_text().strip()
        if not token:
            raise ValueError("The Consul token file is empty")
        return ConsulConfig(self.settings.consul_http_addr.rstrip("/"), token)

    def _registration_payload(self) -> dict:
        address = self.settings.consul_service_address or socket.gethostbyname(
            socket.gethostname()
        )
        port = self.settings.consul_service_port
        name = "orquestador"
        return {
            "ID": self.instance_id,
            "Name": name,
            "Address": address,
            "Port": port,
            # Único servicio público: Traefik lo publica por Consul Catalog con estos
            # tags (contrato 1.6.0), que llegan desde el KV.
            "Tags": self.settings.consul_service_tags,
            "Checks": [
                {
                    "Name": "HTTP health check",
                    "HTTP": f"http://{address}:{port}/health",
                    "Interval": "10s",
                    "Timeout": "3s",
                    "DeregisterCriticalServiceAfter": "1m",
                }
            ],
        }


@dataclass(frozen=True)
class ConsulConfig:
    address: str
    token: str
