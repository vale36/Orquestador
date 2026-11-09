from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def test_la_carpeta_de_los_tokens_sale_de_una_variable():
    # El profesor marcó que el compose dependía de una ruta fija a otro repo
    # (../dockers/consul/generated). La carpeta sale de CONSUL_TOKENS_DIR; el valor por
    # defecto es el de los repos clonados uno al lado del otro.
    text = COMPOSE.read_text(encoding="utf-8")

    carpeta = "${CONSUL_TOKENS_DIR:-../dockers/consul/generated}"
    assert f"file: {carpeta}/orchestrator.token" in text
    assert "file: ../dockers/" not in text
