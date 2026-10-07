"""Logs a stdout (12-Factor XI) con el formato del contrato microservicios-pdf 1.2.0."""

import json
import logging
import logging.config
from contextvars import ContextVar
from pathlib import Path

# logging.json vive en la raíz del repo y se copia a la imagen.
LOGGING_JSON = Path(__file__).resolve().parents[2] / "logging.json"

# El middleware lo fija en cada request. Viaja con el contexto de asyncio, así que
# lo ven también el service y los adaptadores, que no conocen el request.
correlation_id_actual: ContextVar[str] = ContextVar("correlation_id", default="-")

_fabrica_original = logging.getLogRecordFactory()


def _fabrica(*args, **kwargs) -> logging.LogRecord:
    registro = _fabrica_original(*args, **kwargs)
    registro.correlation_id = correlation_id_actual.get()
    return registro


logging.setLogRecordFactory(_fabrica)


def configurar_logs(nivel: str = "INFO") -> None:
    """Carga logging.json con el nivel dado. LOG_LEVEL se aplica en el lifespan,
    cuando Settings ya está validado."""
    logging.config.dictConfig(json.loads(LOGGING_JSON.read_text(encoding="utf-8")))
    logging.getLogger().setLevel(nivel)
