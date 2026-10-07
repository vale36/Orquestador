import logging
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.core.exceptions import DependencyUnavailableError, ExternalServiceError
from tests.doubles import CORRELATION_ID, DOCUMENT, EXTRACTION, REQUEST


def saved_by_this_request():
    """El alta se guardó pero la respuesta no llegó: el documento es de ahora."""
    return replace(DOCUMENT, created_at=datetime.now(UTC))


async def test_successful_flow_returns_the_created_document(ports) -> None:
    result = await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    assert result.document == DOCUMENT
    assert result.extraction_time_ms is None
    assert ports.validation.calls == [(REQUEST, CORRELATION_ID)]
    assert ports.extraction.calls == [(REQUEST, CORRELATION_ID)]
    assert ports.updates.create_calls == [(EXTRACTION, CORRELATION_ID)]


async def test_validation_error_stops_the_flow(ports) -> None:
    ports.validation.error = ExternalServiceError("PDF_INVALID", "no es PDF")

    with pytest.raises(ExternalServiceError):
        await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    assert ports.extraction.calls == []
    assert ports.updates.create_calls == []


async def test_extraction_error_does_not_reach_persistence(ports) -> None:
    ports.extraction.error = ExternalServiceError("PDF_CORRUPTED", "corrupto")

    with pytest.raises(ExternalServiceError):
        await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    assert ports.updates.create_calls == []


async def test_persistence_failure_compensates_and_keeps_the_original_error(
    ports, caplog
) -> None:
    caplog.set_level(logging.INFO)
    ports.updates.error = DependencyUnavailableError("timeout")
    ports.queries.document = saved_by_this_request()

    with pytest.raises(DependencyUnavailableError):
        await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    assert ports.queries.calls == [(EXTRACTION.checksum, CORRELATION_ID)]
    assert ports.updates.delete_calls == [(DOCUMENT.id, CORRELATION_ID)]
    assert "SAGA compensation completed" in caplog.text


async def test_compensation_is_idempotent_when_nothing_was_saved(ports) -> None:
    ports.updates.error = DependencyUnavailableError("timeout")

    with pytest.raises(DependencyUnavailableError):
        await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    assert ports.updates.delete_calls == []


async def test_a_failed_compensation_is_logged_and_the_original_error_kept(
    ports, caplog
) -> None:
    ports.updates.error = DependencyUnavailableError("timeout")
    ports.updates.delete_error = DependencyUnavailableError("sigue caido")
    ports.queries.document = saved_by_this_request()

    with pytest.raises(DependencyUnavailableError, match="timeout"):
        await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    assert "SAGA compensation failed" in caplog.text


@pytest.mark.parametrize("code", ["DUPLICATE_CHECKSUM", "VALIDATION_ERROR"])
async def test_contract_errors_from_persistence_are_not_compensated(
    ports, code
) -> None:
    # Persistencia respondió que no guardó nada: no hay operación parcial que deshacer.
    # Ante un 409, borrar por checksum eliminaría el documento que ya existía.
    ports.updates.error = ExternalServiceError(code, "rechazado")
    ports.queries.document = saved_by_this_request()

    with pytest.raises(ExternalServiceError):
        await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    assert ports.queries.calls == []
    assert ports.updates.delete_calls == []


async def test_a_document_saved_before_this_request_is_not_deleted(ports) -> None:
    ports.updates.error = DependencyUnavailableError("timeout")
    ports.queries.document = DOCUMENT  # created_at de 2026-09-14

    with pytest.raises(DependencyUnavailableError):
        await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    assert ports.updates.delete_calls == []


async def test_the_extraction_time_is_returned_with_the_document(ports) -> None:
    ports.extraction.result = replace(EXTRACTION, extraction_time_ms=12.5)

    result = await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    assert result.document == DOCUMENT
    assert result.extraction_time_ms == 12.5
