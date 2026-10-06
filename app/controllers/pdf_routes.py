from dataclasses import asdict

from fastapi import APIRouter, Depends, Request, status

from app.core.composition import get_orchestrator_service
from app.models.pdf_document import PdfRequest
from app.schemas.pdf_schemas import (
    ErrorResponseSchema,
    PdfDocumentResponseSchema,
    PdfRequestSchema,
)
from app.services.orchestrator import OrchestratorService

router = APIRouter(tags=["PDF"])


@router.post(
    "/pdf",
    response_model=PdfDocumentResponseSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponseSchema, "description": "Request inválido."},
        409: {"model": ErrorResponseSchema, "description": "PDF ya guardado."},
        413: {"model": ErrorResponseSchema, "description": "PDF demasiado grande."},
        422: {"model": ErrorResponseSchema, "description": "PDF inválido o corrupto."},
        503: {"model": ErrorResponseSchema, "description": "Dependencia caída."},
    },
)
async def create_pdf(
    pdf_request: PdfRequestSchema,
    request: Request,
    orchestrator_service: OrchestratorService = Depends(get_orchestrator_service),
) -> PdfDocumentResponseSchema:
    document = await orchestrator_service.orchestrate(
        PdfRequest(
            archivo_base64=pdf_request.archivo_base64, nombre=pdf_request.nombre
        ),
        request.state.correlation_id,
    )
    return PdfDocumentResponseSchema.model_validate(asdict(document))
