from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.controllers.pdf_routes import router as pdf_router
from app.core.composition import build_orchestrator, get_settings
from app.core.exceptions import ExternalServiceError
from app.schemas.pdf_schemas import ErrorResponseSchema, ServiceErrorSchema


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Settings se valida al arrancar: una variable faltante impide iniciar la app.
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as http:
        app.state.orchestrator_service = build_orchestrator(settings, http)
        yield


app = FastAPI(
    title="Orquestador",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(pdf_router)


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
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


def error_response(
    request: Request, status_code: int, code: str, message: str, details: dict
) -> JSONResponse:
    """Formato común de errores. El header se agrega acá porque el handler de
    Exception corre fuera del middleware de correlation ID."""
    correlation_id = request.state.correlation_id
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
async def unexpected_error_handler(request: Request, _: Exception) -> JSONResponse:
    return error_response(
        request, 500, "INTERNAL_ERROR", "Error interno del orquestador", {}
    )
