"""Lectura de la configuración desde el KV de Consul (contrato 1.6.0)."""

import base64
from pathlib import Path

import httpx


def leer_config_de_consul(
    direccion: str,
    archivo_token: str | Path,
    servicio: str,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, str]:
    """Devuelve las claves de config/<servicio>/ en minúsculas, como los campos de
    Settings. Sin claves la app no arranca: la configuración no se cargó en Consul.
    Los valores no se registran en logs (pueden traer URIs)."""
    prefijo = f"config/{servicio}/"
    token = Path(archivo_token).read_text(encoding="utf-8").strip()
    with httpx.Client(timeout=3, transport=transport) as cliente:
        respuesta = cliente.get(
            f"{direccion.rstrip('/')}/v1/kv/{prefijo}",
            params={"recurse": "true"},
            headers={"X-Consul-Token": token},
        )
    if respuesta.status_code == 404:
        raise RuntimeError(f"no hay configuración en Consul bajo {prefijo}")
    respuesta.raise_for_status()
    valores = {}
    for entrada in respuesta.json():
        if entrada["Key"] == prefijo or entrada["Value"] is None:
            continue
        clave = entrada["Key"].removeprefix(prefijo).lower()
        valores[clave] = base64.b64decode(entrada["Value"]).decode("utf-8")
    return valores
