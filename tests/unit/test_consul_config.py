"""Contrato 1.6.0: con Consul, la configuración sale del KV (config/orquestador/) y
del entorno solo llega cómo conectarse a Consul."""

import base64
from pathlib import Path

import httpx
import pytest

from app.core import consul_config
from app.core.config import cargar_settings


def _entrada(clave: str, valor: str | None) -> dict:
    if valor is None:
        return {"Key": clave, "Value": None}
    return {"Key": clave, "Value": base64.b64encode(valor.encode()).decode()}


def _token(tmp_path: Path) -> Path:
    archivo = tmp_path / "consul.token"
    archivo.write_text("test-token\n", encoding="utf-8")
    return archivo


def test_lee_las_claves_del_servicio_con_su_token(tmp_path: Path):
    pedidos = []

    def responder(request: httpx.Request) -> httpx.Response:
        pedidos.append(request)
        return httpx.Response(
            200,
            json=[
                _entrada("config/orquestador/", None),
                _entrada("config/orquestador/REQUEST_TIMEOUT_SECONDS", "7"),
                _entrada("config/orquestador/LOG_LEVEL", "DEBUG"),
            ],
        )

    valores = consul_config.leer_config_de_consul(
        "http://consul:8500/",
        _token(tmp_path),
        "orquestador",
        transport=httpx.MockTransport(responder),
    )

    assert valores == {"request_timeout_seconds": "7", "log_level": "DEBUG"}
    assert pedidos[0].url.path == "/v1/kv/config/orquestador/"
    assert pedidos[0].url.params["recurse"] == "true"
    assert pedidos[0].headers["X-Consul-Token"] == "test-token"


def test_sin_configuracion_cargada_en_consul_no_arranca(tmp_path: Path):
    with pytest.raises(RuntimeError, match="config/orquestador/"):
        consul_config.leer_config_de_consul(
            "http://consul:8500",
            _token(tmp_path),
            "orquestador",
            transport=httpx.MockTransport(lambda _: httpx.Response(404)),
        )


def test_con_consul_la_configuracion_del_kv_tiene_prioridad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("CONSUL_ENABLED", "true")
    monkeypatch.setenv("CONSUL_HTTP_TOKEN_FILE", str(_token(tmp_path)))
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "5")
    kv = [_entrada("config/orquestador/REQUEST_TIMEOUT_SECONDS", "9")]

    settings = cargar_settings(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=kv))
    )

    assert settings.request_timeout_seconds == 9


def test_los_tags_de_traefik_llegan_del_kv_como_lista(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Los labels de Traefik ya no están en el compose: son tags guardados en Consul."""
    monkeypatch.setenv("CONSUL_ENABLED", "true")
    monkeypatch.setenv("CONSUL_HTTP_TOKEN_FILE", str(_token(tmp_path)))
    tags = '["traefik.enable=true", "traefik.http.routers.orquestador.tls=true"]'
    kv = [_entrada("config/orquestador/CONSUL_SERVICE_TAGS", tags)]

    settings = cargar_settings(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=kv))
    )

    assert settings.consul_service_tags == [
        "traefik.enable=true",
        "traefik.http.routers.orquestador.tls=true",
    ]


def test_sin_consul_la_configuracion_sale_del_entorno(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CONSUL_ENABLED", "false")
    monkeypatch.setenv("REQUEST_TIMEOUT_SECONDS", "3")

    def no_llamar(_: httpx.Request) -> httpx.Response:
        raise AssertionError("sin Consul no se consulta el KV")

    settings = cargar_settings(transport=httpx.MockTransport(no_llamar))

    assert settings.request_timeout_seconds == 3
    assert settings.consul_service_tags == []
