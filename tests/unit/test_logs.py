import logging

import pytest

from app.core.logs import configurar_logs, correlation_id_actual


@pytest.fixture
def logging_restaurado():
    """configurar_logs reemplaza los handlers del root: se restauran al terminar."""
    root = logging.getLogger()
    handlers, nivel = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(nivel)


def test_configurar_logs_aplica_el_nivel(logging_restaurado) -> None:
    configurar_logs("DEBUG")

    assert logging.getLogger().level == logging.DEBUG


def test_logging_json_da_el_formato_del_contrato(logging_restaurado, capsys) -> None:
    configurar_logs("INFO")
    token = correlation_id_actual.set("cid-123")
    try:
        logging.getLogger("prueba").info("evento clave=valor")
    finally:
        correlation_id_actual.reset(token)

    assert "INFO prueba correlation_id=cid-123 evento clave=valor" in (
        capsys.readouterr().out
    )
