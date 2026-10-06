import httpx
import pytest

from app.core.composition import get_orchestrator_service
from app.core.config import Settings
from app.main import app
from tests.doubles import Ports


@pytest.fixture(autouse=True)
def entorno_de_test(monkeypatch):
    """Configuración hermética: ignora el .env local y fija las variables."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for nombre, valor in {
        "VALIDACION_URL": "http://validacion.test",
        "EXTRACCION_URL": "http://extraccion.test",
        "PERSISTENCIA_CONSULTAS_URL": "http://consultas.test",
        "PERSISTENCIA_ACTUALIZACIONES_URL": "http://actualizaciones.test",
        "REQUEST_TIMEOUT_SECONDS": "1",
        "RETRY_ATTEMPTS": "0",
        "RETRY_DELAY_SECONDS": "0",
    }.items():
        monkeypatch.setenv(nombre, valor)


@pytest.fixture
def ports() -> Ports:
    return Ports()


@pytest.fixture
async def client(ports: Ports):
    """Cliente HTTP contra la app real, con los puertos sustituidos por dobles."""
    service = ports.service()
    app.dependency_overrides[get_orchestrator_service] = lambda: service
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()
