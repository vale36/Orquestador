import logging
import sys
from contextvars import ContextVar

# El middleware lo fija en cada request. Viaja con el contexto de asyncio, así que
# lo ven también el service y los adaptadores, que no conocen el request.
correlation_id_actual: ContextVar[str] = ContextVar("correlation_id", default="-")


def configurar_logs() -> None:
    """Logs a stdout (12-Factor XI); cada registro lleva el correlation_id."""
    fabrica_original = logging.getLogRecordFactory()

    def fabrica(*args, **kwargs) -> logging.LogRecord:
        registro = fabrica_original(*args, **kwargs)
        registro.correlation_id = correlation_id_actual.get()
        return registro

    logging.setLogRecordFactory(fabrica)
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "correlation_id=%(correlation_id)s %(message)s"
        ),
    )
