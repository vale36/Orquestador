import logging
import socket
import time
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.controllers.pdf_routes import router as pdf_router
from app.core.composition import build_orchestrator, get_settings
from app.core.config import Settings
from app.core.consul_registry import ConsulRegistry
from app.core.exceptions import ExternalServiceError
from app.core.logs import configurar_logs, correlation_id_actual
from app.schemas.pdf_schemas import (
    MAX_PDF_SIZE_BYTES,
    MAX_REQUEST_BODY_BYTES,
    ErrorResponseSchema,
    ServiceErrorSchema,
)

configurar_logs()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Settings se valida al arrancar: una variable faltante impide iniciar la app.
    settings = get_settings()
    logging.getLogger().setLevel(settings.log_level)
    registry = _consul_registry(settings)
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as http:
        app.state.orchestrator_service = build_orchestrator(settings, http)
        if registry:
            await registry.register()
        logger.info("servicio iniciado")
        yield
        # uvicorn llega acá ante SIGTERM, después de cerrar el puerto y terminar las
        # requests en curso (12-Factor IX). Primero sale de Consul, así Traefik deja de
        # mandarle tráfico; al salir del bloque se cierra httpx.
        logger.info("apagado iniciado")
        if registry:
            try:
                await registry.deregister()
            except Exception:
                logger.exception("no se pudo deregistrar el servicio de Consul")
    logger.info("apagado completo")


def _consul_registry(settings: Settings) -> ConsulRegistry | None:
    if not settings.consul_enabled:
        return None
    return ConsulRegistry(
        settings=settings, instance_id=f"orquestador-{socket.gethostname()}"
    )


class RequestBodyLimitMiddleware:
    def __init__(self, app, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope, receive, send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != "/pdf"
        ):
            await self.app(scope, receive, send)
            return

        if self._content_length_exceeds_limit(scope):
            await self._reject(scope, receive, send)
            return

        received_bytes = 0
        oversized = False

        async def limited_receive():
            nonlocal received_bytes, oversized
            if oversized:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_size:
                    oversized = True
                    await self._reject(scope, receive, send)
                    return {"type": "http.disconnect"}
            return message

        async def limited_send(message) -> None:
            if not oversized:
                await send(message)

        await self.app(scope, limited_receive, limited_send)

    def _content_length_exceeds_limit(self, scope) -> bool:
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    if int(value) > self.max_body_size:
                        return True
                except ValueError:
                    continue
        return False

    async def _reject(self, scope, receive, send) -> None:
        request = Request(scope)
        response = error_response(
            request,
            413,
            "PDF_TOO_LARGE",
            "El PDF supera el tamaño máximo permitido",
            {"max_size_bytes": MAX_PDF_SIZE_BYTES},
        )
        await response(scope, receive, send)


app = FastAPI(
    title="Orquestador",
    version="1.1.0",
    lifespan=lifespan,
)
app.include_router(pdf_router)
app.add_middleware(
    RequestBodyLimitMiddleware, max_body_size=MAX_REQUEST_BODY_BYTES
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# Tabla de errores comunes del contrato microservicios-pdf: el status sale del código,
# así el error de una dependencia llega al cliente con el mismo significado.
CONTRACT_ERROR_STATUS = {
    "VALIDATION_ERROR": 400,
    "PDF_INVALID": 422,
    "PDF_TOO_LARGE": 413,
    "PDF_CORRUPTED": 422,
    "RESOURCE_NOT_FOUND": 404,
    "DUPLICATE_CHECKSUM": 409,
    "DEPENDENCY_UNAVAILABLE": 503,
    "DATABASE_ERROR": 503,
    "INTERNAL_ERROR": 500,
}


def _correlation_id_from(header: str | None) -> str:
    """Contrato: identificación UUID. Un valor ausente o que no es UUID se
    reemplaza por uno nuevo en lugar de rechazar el request."""
    try:
        return str(UUID(header)) if header else str(uuid4())
    except ValueError:
        return str(uuid4())


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    correlation_id = _correlation_id_from(request.headers.get("X-Correlation-ID"))
    request.state.correlation_id = correlation_id
    token = correlation_id_actual.set(correlation_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info(
            "method=%s path=%s status=%s duracion_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
        )
        return response
    finally:
        correlation_id_actual.reset(token)


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict,
    exc_info: BaseException | None = None,
) -> JSONResponse:
    """Formato común de errores. El header y el contexto del log se fijan acá
    porque el handler de Exception corre fuera del middleware de correlation ID."""
    correlation_id = request.state.correlation_id
    token = correlation_id_actual.set(correlation_id)
    # ERROR solo para fallas no previstas; un error del contrato devuelto al cliente es
    # recuperable (WARNING, contrato 1.2.0), aunque sea un 503.
    logger.log(
        logging.ERROR if exc_info is not None else logging.WARNING,
        "code=%s status=%s message=%s",
        code,
        status_code,
        message,
        exc_info=exc_info,
    )
    correlation_id_actual.reset(token)
    response = ErrorResponseSchema(
        error=ServiceErrorSchema(
            code=code,
            message=message,
            details=details,
            correlation_id=UUID(correlation_id),
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
        headers={"X-Correlation-ID": correlation_id},
    )


@app.exception_handler(ExternalServiceError)
async def external_service_error_handler(
    request: Request, error: ExternalServiceError
) -> JSONResponse:
    status_code = CONTRACT_ERROR_STATUS.get(error.code, 500)
    return error_response(
        request, status_code, error.code, error.message, error.details
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    # Sin el valor recibido: el input puede traer el PDF entero en Base64.
    if any(item["type"] == "pdf_too_large" for item in error.errors()):
        return error_response(
            request,
            413,
            "PDF_TOO_LARGE",
            "El PDF supera el tamaño máximo permitido",
            {"max_size_bytes": MAX_PDF_SIZE_BYTES},
        )
    errors = [
        {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
        for item in error.errors()
    ]
    return error_response(
        request,
        400,
        "VALIDATION_ERROR",
        "La solicitud no cumple el contrato",
        {"errors": errors},
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, error: Exception) -> JSONResponse:
    return error_response(
        request, 500, "INTERNAL_ERROR", "Error interno del orquestador", {}, error
    )
