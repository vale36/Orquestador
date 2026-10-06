"""Traducción entre el JSON del contrato y los modelos de dominio."""

from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from app.core.exceptions import DependencyUnavailableError
from app.models.pdf_document import ExtractionResult, PdfDocument


def extraction_result_from_json(data: dict, service_name: str) -> ExtractionResult:
    try:
        return ExtractionResult(
            nombre=data["nombre"],
            texto=data["texto"],
            checksum=data["checksum"],
            tamano_bytes=data["tamano_bytes"],
            paginas=data["paginas"],
        )
    except (KeyError, TypeError) as error:
        raise _invalid(service_name) from error


def document_from_json(data: dict, service_name: str) -> PdfDocument:
    try:
        return PdfDocument(
            id=UUID(data["id"]),
            nombre=data["nombre"],
            checksum=data["checksum"],
            texto=data["texto"],
            tamano_bytes=data["tamano_bytes"],
            paginas=data["paginas"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _invalid(service_name) from error


def extraction_result_to_json(result: ExtractionResult) -> dict:
    return asdict(result)


def _invalid(service_name: str) -> DependencyUnavailableError:
    return DependencyUnavailableError(
        f"{service_name} respondió un documento fuera del contrato"
    )
