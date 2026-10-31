import httpx
import pytest

from app.core.consul_service_discovery import (
    ConsulServiceDiscovery,
    OptionalFallbackEndpointResolver,
)
from app.core.exceptions import DependencyUnavailableError


def consul_response(*addresses: tuple[str, int]) -> list[dict]:
    return [
        {
            "Node": {"Node": f"node-{port}"},
            "Service": {"Address": address, "Port": port},
            "Checks": [{"Status": "passing"}],
        }
        for address, port in addresses
    ]


async def test_resolves_healthy_instances_and_sends_the_acl_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=consul_response(("extraccion-a", 8000), ("extraccion-b", 8001)),
        )

    discovery = ConsulServiceDiscovery(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://consul:8500",
        token="secret-test-token",
    )

    endpoints = await discovery.resolve("extraccion")

    assert [str(endpoint) for endpoint in endpoints] == [
        "http://extraccion-a:8000",
        "http://extraccion-b:8001",
    ]
    assert str(requests[0].url) == (
        "http://consul:8500/v1/health/service/extraccion?passing=true"
    )
    assert requests[0].headers["X-Consul-Token"] == "secret-test-token"


async def test_returns_instances_in_rolling_selection_order() -> None:
    discovery = ConsulServiceDiscovery(
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200,
                    json=consul_response(
                        ("extraccion-a", 8000), ("extraccion-b", 8000)
                    ),
                )
            )
        ),
        base_url="http://consul:8500",
        token=None,
    )

    first = await discovery.resolve("extraccion")
    second = await discovery.resolve("extraccion")

    assert [str(endpoint) for endpoint in first] == [
        "http://extraccion-a:8000",
        "http://extraccion-b:8000",
    ]
    assert [str(endpoint) for endpoint in second] == [
        "http://extraccion-b:8000",
        "http://extraccion-a:8000",
    ]


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(200, json=[]), "no tiene instancias saludables"),
        (httpx.Response(403, text="denied"), "no pudo consultar"),
    ],
)
async def test_discovery_failures_use_existing_dependency_error(
    response: httpx.Response, message: str
) -> None:
    discovery = ConsulServiceDiscovery(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)),
        base_url="http://consul:8500",
        token=None,
    )

    with pytest.raises(DependencyUnavailableError, match=message):
        await discovery.resolve("extraccion")


async def test_optional_fallback_is_used_only_when_explicitly_configured() -> None:
    discovery = ConsulServiceDiscovery(
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[]))
        ),
        base_url="http://consul:8500",
        token=None,
    )
    resolver = OptionalFallbackEndpointResolver(
        discovery,
        fallback_url="http://extraccion-fixed:8000",
    )

    endpoints = await resolver.resolve("extraccion")

    assert endpoints == [httpx.URL("http://extraccion-fixed:8000")]


async def test_unreachable_consul_uses_existing_dependency_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("consul no responde")

    discovery = ConsulServiceDiscovery(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        base_url="http://consul:8500",
        token=None,
    )

    with pytest.raises(DependencyUnavailableError, match="no pudo consultar"):
        await discovery.resolve("extraccion")


class Reloj:
    """Reloj manual para probar la caché sin esperar."""

    def __init__(self) -> None:
        self.ahora = 0.0

    def __call__(self) -> float:
        return self.ahora


def contar_consultas(requests: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200, json=consul_response(("extraccion-a", 8000), ("extraccion-b", 8000))
        )

    return handler


async def test_reuses_the_healthy_instances_for_a_couple_of_seconds() -> None:
    # Cada PDF hace cuatro llamadas: sin caché serían cuatro consultas más a Consul.
    requests: list[httpx.Request] = []
    reloj = Reloj()
    discovery = ConsulServiceDiscovery(
        httpx.AsyncClient(transport=httpx.MockTransport(contar_consultas(requests))),
        base_url="http://consul:8500",
        token=None,
        reloj=reloj,
    )

    primera = await discovery.resolve("extraccion")
    reloj.ahora = 1.5
    segunda = await discovery.resolve("extraccion")

    assert len(requests) == 1
    # Sigue rotando entre las instancias aunque la lista venga de la caché.
    assert primera[0] != segunda[0]


async def test_asks_consul_again_once_the_cache_expires() -> None:
    requests: list[httpx.Request] = []
    reloj = Reloj()
    discovery = ConsulServiceDiscovery(
        httpx.AsyncClient(transport=httpx.MockTransport(contar_consultas(requests))),
        base_url="http://consul:8500",
        token=None,
        reloj=reloj,
    )

    await discovery.resolve("extraccion")
    reloj.ahora = 2.5
    await discovery.resolve("extraccion")

    assert len(requests) == 2
