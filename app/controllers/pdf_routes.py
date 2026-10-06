from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.schemas.pdf_schemas import (
    ErrorResponseSchema,
    PdfDocumentResponseSchema,
    PdfRequestSchema,
)
from app.services.dependencies import get_orchestrator_service
from app.services.orchestrator import OrchestratorService

router = APIRouter(tags=["PDF"])


@router.post(
    "/pdf",
    response_model=PdfDocumentResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        422: {
            "model": ErrorResponseSchema,
            "description": "La solicitud o validación del PDF fue rechazada.",
        },
        502: {
            "model": ErrorResponseSchema,
            "description": "Falló el procesamiento del PDF en una dependencia.",
        },
        503: {
            "model": ErrorResponseSchema,
            "description": "Una dependencia no está disponible.",
        },
    },
)
def create_pdf(
    pdf_request: PdfRequestSchema,
    request: Request,
    response: Response,
    correlation_id: UUID | None = Header(default=None, alias="X-Correlation-ID"),
    orchestrator_service: OrchestratorService = Depends(get_orchestrator_service),
) -> PdfDocumentResponseSchema:
    request_correlation_id = str(correlation_id or uuid4())
    request.state.correlation_id = request_correlation_id
    response.headers["X-Correlation-ID"] = request_correlation_id
    return orchestrator_service.orchestrate(
        pdf_request,
        request_correlation_id,
    )
