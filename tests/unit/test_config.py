import pytest
from pydantic import ValidationError

from app.core.config import Settings

VARIABLES = {
    "VALIDACION_URL": "http://validacion-pdf:8000",
    "EXTRACCION_URL": "http://extraccion-texto:8000",
    "PERSISTENCIA_CONSULTAS_URL": "http://persistencia-consultas:8000",
    "PERSISTENCIA_ACTUALIZACIONES_URL": "http://persistencia-actualizaciones:8000",
    "REQUEST_TIMEOUT_SECONDS": "5",
    "RETRY_ATTEMPTS": "2",
    "RETRY_DELAY_SECONDS": "0.5",
}


@pytest.fixture
def entorno(monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for nombre, valor in VARIABLES.items():
        monkeypatch.setenv(nombre, valor)
    return monkeypatch


def test_settings_reads_the_contract_variables(entorno) -> None:
    settings = Settings()

    assert settings.validacion_url == "http://validacion-pdf:8000"
    assert settings.extraccion_url == "http://extraccion-texto:8000"
    assert settings.persistencia_consultas_url == "http://persistencia-consultas:8000"
    assert (
        settings.persistencia_actualizaciones_url
        == "http://persistencia-actualizaciones:8000"
    )
    assert settings.request_timeout_seconds == 5
    assert settings.retry_attempts == 2
    assert settings.retry_delay_seconds == 0.5


@pytest.mark.parametrize("nombre", list(VARIABLES))
def test_settings_fails_when_a_variable_is_missing(entorno, nombre) -> None:
    entorno.delenv(nombre)

    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize(
    ("nombre", "valor"),
    [
        ("REQUEST_TIMEOUT_SECONDS", "0"),
        ("RETRY_ATTEMPTS", "-1"),
        ("RETRY_DELAY_SECONDS", "-0.1"),
    ],
)
def test_settings_rejects_invalid_values(entorno, nombre, valor) -> None:
    entorno.setenv(nombre, valor)

    with pytest.raises(ValidationError):
        Settings()


def test_log_level_es_opcional_e_info_por_defecto(entorno) -> None:
    assert Settings().log_level == "INFO"


def test_log_level_invalido_impide_arrancar(entorno) -> None:
    entorno.setenv("LOG_LEVEL", "VERBOSE")

    with pytest.raises(ValidationError):
        Settings()
