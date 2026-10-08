import logging

from tests.doubles import CORRELATION_ID, DOCUMENT_ID, EXTRACTION, REQUEST


def messages(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records]


async def test_successful_flow_logs_each_step(ports, caplog) -> None:
    caplog.set_level(logging.INFO)

    await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    logged = messages(caplog)
    assert "validacion aceptada" in logged
    assert (
        f"texto extraido paginas={EXTRACTION.paginas} checksum={EXTRACTION.checksum}"
        in logged
    )
    assert f"documento creado id={DOCUMENT_ID} checksum={EXTRACTION.checksum}" in (
        logged
    )


async def test_logs_do_not_include_sensitive_data(ports, caplog) -> None:
    caplog.set_level(logging.DEBUG)

    await ports.service().orchestrate(REQUEST, CORRELATION_ID)

    everything = "\n".join(messages(caplog))
    assert REQUEST.nombre not in everything
    assert EXTRACTION.nombre not in everything
    assert EXTRACTION.texto not in everything
    assert REQUEST.archivo_base64 not in everything
