from uuid import UUID, uuid4

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.controllers.pdf_routes import router as pdf_router
from app.schemas.pdf_schemas import ErrorResponseSchema, ServiceErrorSchema
from app.services.ports import (
    DependencyUnavailableError,
    ExternalServiceError,
    ExtractionServiceError,
    PersistenceServiceError,
    ValidationServiceError,
)

app = FastAPI(
    title="Orquestador",
    version="1.0.0",
)
app.include_router(pdf_router)

SERVICE_ERROR_STATUS = {
    ValidationServiceError: 422,
    ExtractionServiceError: status.HTTP_502_BAD_GATEWAY,
    PersistenceServiceError: status.HTTP_502_BAD_GATEWAY,
    DependencyUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _request_correlation_id(request: Request) -> str:
    correlation_id = getattr(request.state, "correlation_id", None)
    if correlation_id is None:
        supplied_id = request.headers.get("X-Correlation-ID")
        try:
            correlation_id = str(UUID(supplied_id)) if supplied_id else str(uuid4())
        except ValueError:
            correlation_id = str(uuid4())
        request.state.correlation_id = correlation_id
    return correlation_id


@app.exception_handler(ExternalServiceError)
async def external_service_error_handler(
    request: Request,
    error: ExternalServiceError,
) -> JSONResponse:
    response_status = SERVICE_ERROR_STATUS.get(
        type(error),
        status.HTTP_502_BAD_GATEWAY,
    )
    response = ErrorResponseSchema(error=error.error)
    return JSONResponse(
        status_code=response_status,
        content=response.model_dump(mode="json"),
        headers={"X-Correlation-ID": _request_correlation_id(request)},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    correlation_id = _request_correlation_id(request)
    response = ErrorResponseSchema(
        error=ServiceErrorSchema(
            code="REQUEST_VALIDATION_ERROR",
            message="La solicitud no cumple el contrato",
            details={
                "errors": [
                    {
                        "loc": list(item["loc"]),
                        "msg": item["msg"],
                        "type": item["type"],
                    }
                    for item in error.errors()
                ]
            },
            correlation_id=UUID(correlation_id),
        )
    )
    return JSONResponse(
        status_code=422,
        content=response.model_dump(mode="json"),
        headers={"X-Correlation-ID": correlation_id},
    )
