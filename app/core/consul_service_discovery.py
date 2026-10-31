"""Descubrimiento de instancias sanas del Orquestador mediante Consul."""

import time
from collections import defaultdict
from collections.abc import Callable

import httpx

from app.core.exceptions import DependencyUnavailableError

# Cada PDF hace cuatro llamadas: guardar la lista de instancias sanas un par de segundos
# evita una consulta a Consul por llamada. Si una instancia cae en ese lapso, la cubre
# el reintento (va a la siguiente) y después Consul deja de devolverla.
CACHE_SEGUNDOS = 2.0


class ConsulServiceDiscovery:
    """Resuelve endpoints desde el health API, con una caché corta por servicio."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        token: str | None,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._reloj = reloj
        self._next_index: dict[str, int] = defaultdict(int)
        self._cache: dict[str, tuple[float, list[tuple[str, int]]]] = {}

    async def resolve(self, service_name: str) -> list[httpx.URL]:
        endpoints = await self._sanos(service_name)
        start = self._next_index[service_name] % len(endpoints)
        self._next_index[service_name] += 1
        ordered = endpoints[start:] + endpoints[:start]
        return [httpx.URL(f"http://{address}:{port}") for address, port in ordered]

    async def _sanos(self, service_name: str) -> list[tuple[str, int]]:
        guardado = self._cache.get(service_name)
        if guardado and self._reloj() - guardado[0] < CACHE_SEGUNDOS:
            return guardado[1]
        headers = {"X-Consul-Token": self._token} if self._token else None
        try:
            response = await self._client.get(
                f"{self._base_url}/v1/health/service/{service_name}",
                params={"passing": "true"},
                headers=headers,
            )
        except httpx.HTTPError as error:
            raise DependencyUnavailableError(
                f"Consul no pudo consultar el servicio {service_name}"
            ) from error

        if not response.is_success:
            raise DependencyUnavailableError(
                f"Consul no pudo consultar el servicio {service_name}: "
                f"HTTP {response.status_code}"
            )

        try:
            registrations = response.json()
        except ValueError as error:
            raise DependencyUnavailableError(
                f"Consul respondió datos inválidos para {service_name}"
            ) from error

        endpoints = self._healthy_endpoints(registrations)
        if not endpoints:
            raise DependencyUnavailableError(
                f"El servicio {service_name} no tiene instancias saludables"
            )
        # Solo se guardan las respuestas buenas: un error se vuelve a consultar.
        self._cache[service_name] = (self._reloj(), endpoints)
        return endpoints

    @staticmethod
    def _healthy_endpoints(registrations: object) -> list[tuple[str, int]]:
        if not isinstance(registrations, list):
            return []

        endpoints: set[tuple[str, int]] = set()
        for registration in registrations:
            if not isinstance(registration, dict):
                continue
            checks = registration.get("Checks", [])
            if not isinstance(checks, list) or not all(
                isinstance(check, dict) and check.get("Status") == "passing"
                for check in checks
            ):
                continue
            service = registration.get("Service")
            if not isinstance(service, dict):
                continue
            address = service.get("Address")
            port = service.get("Port")
            if isinstance(address, str) and address and isinstance(port, int):
                endpoints.add((address, port))

        return sorted(endpoints)


class OptionalFallbackEndpointResolver:
    """Usa una URL fija solo como fallback explícitamente habilitado."""

    def __init__(
        self,
        discovery: ConsulServiceDiscovery,
        fallback_url: str,
    ) -> None:
        self._discovery = discovery
        self._fallback_url = fallback_url.rstrip("/")

    async def resolve(self, service_name: str) -> list[httpx.URL]:
        try:
            return await self._discovery.resolve(service_name)
        except DependencyUnavailableError:
            return [httpx.URL(self._fallback_url)]
