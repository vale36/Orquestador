import logging

import pytest
from fastapi.testclient import TestClient

from app.core.composition import get_settings
from app.core.consul_registry import ConsulRegistry
from app.main import app


@pytest.fixture(autouse=True)
def settings_y_nivel_restaurados():
    """get_settings se cachea y el lifespan cambia el nivel del root: se restauran."""
    root = logging.getLogger()
    nivel = root.level
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    root.setLevel(nivel)


def test_lifespan_logs_startup_and_ordered_shutdown(caplog) -> None:
    caplog.set_level(logging.INFO)

    with TestClient(app):
        pass

    logged = [record.getMessage() for record in caplog.records]
    assert "servicio iniciado" in logged
    assert logged.index("apagado iniciado") < logged.index("apagado completo")


def test_lifespan_applies_log_level(monkeypatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    with TestClient(app):
        assert logging.getLogger().level == logging.WARNING


def test_lifespan_registra_en_consul_y_deregistra_al_apagar(
    monkeypatch, tmp_path
) -> None:
    eventos = []
    token = tmp_path / "orchestrator.token"
    token.write_text("test-token", encoding="utf-8")
    monkeypatch.setenv("CONSUL_ENABLED", "true")
    monkeypatch.setenv("CONSUL_HTTP_TOKEN_FILE", str(token))
    # La configuración ya está en el entorno; el KV de Consul no agrega claves.
    monkeypatch.setattr(
        "app.core.config.leer_config_de_consul", lambda *_: {}, raising=False
    )

    async def registrar(self):
        eventos.append("registrado")

    async def deregistrar(self):
        eventos.append("deregistrado")

    monkeypatch.setattr(ConsulRegistry, "register", registrar)
    monkeypatch.setattr(ConsulRegistry, "deregister", deregistrar)

    with TestClient(app):
        assert eventos == ["registrado"]

    assert eventos == ["registrado", "deregistrado"]
