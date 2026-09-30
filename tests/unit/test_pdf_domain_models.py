import ast
import inspect
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from typing import get_type_hints
from uuid import UUID

from app.models.pdf_document import PdfDocument


def test_pdf_document_is_a_pure_domain_dataclass() -> None:
    assert is_dataclass(PdfDocument)
    assert [field.name for field in fields(PdfDocument)] == [
        "id",
        "nombre",
        "checksum",
        "texto",
        "tamano_bytes",
        "paginas",
        "created_at",
        "updated_at",
    ]

    source_module = inspect.getmodule(PdfDocument)
    assert source_module is not None
    module = ast.parse(inspect.getsource(source_module))
    imported_modules = {
        alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "pydantic" not in imported_modules

    class_node = next(
        node for node in module.body if isinstance(node, ast.ClassDef)
    )
    decorator_names = {
        decorator.id
        for node in ast.walk(class_node)
        for decorator in getattr(node, "decorator_list", [])
        if isinstance(decorator, ast.Name)
    }
    assert decorator_names <= {"dataclass"}
    assert get_type_hints(PdfDocument) == {
        "id": UUID,
        "nombre": str,
        "checksum": str,
        "texto": str,
        "tamano_bytes": int,
        "paginas": int,
        "created_at": datetime,
        "updated_at": datetime,
    }


def test_pdf_document_represents_shared_document_contract() -> None:
    identifier = UUID("8f6f7c3e-12d5-4f57-9c6c-123456789abc")
    created_at = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)

    document = PdfDocument(
        id=identifier,
        nombre="contrato.pdf",
        checksum="a7f5f35426b927411fc9231b56382173",
        texto="Contenido extraído del PDF",
        tamano_bytes=245760,
        paginas=3,
        created_at=created_at,
        updated_at=updated_at,
    )

    assert document.id == identifier
    assert isinstance(document.id, UUID)
    assert document.nombre == "contrato.pdf"
    assert document.checksum == "a7f5f35426b927411fc9231b56382173"
    assert document.texto == "Contenido extraído del PDF"
    assert document.tamano_bytes == 245760
    assert document.paginas == 3
    assert document.created_at.tzinfo == timezone.utc
    assert document.updated_at.tzinfo == timezone.utc
