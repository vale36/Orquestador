"""Configuration entry point for the orchestrator service."""

import json
from pathlib import Path
from typing import Literal

import httpx
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.consul_config import leer_config_de_consul


class ConexionConsul(BaseSettings):
    """Lo único que llega por el entorno cuando hay Consul: cómo conectarse."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    consul_enabled: bool = False
    consul_http_addr: str = "http://consul:8500"
    consul_http_token_file: Path | None = None


class Settings(ConexionConsul):
    """Variables del contrato. Obligatorias salvo LOG_LEVEL: si falta una, la app no
    arranca."""

    validacion_url: str | None = None
    extraccion_url: str | None = None
    persistencia_consultas_url: str | None = None
    persistencia_actualizaciones_url: str | None = None
    consul_fallback_enabled: bool = False
    # Contrato 1.6.0: registro propio en Consul. Los tags son las reglas de Traefik
    # (antes labels del compose); en el KV se guardan como lista JSON.
    consul_service_address: str | None = None
    consul_service_port: int = 8000
    consul_service_tags: list[str] = []
    request_timeout_seconds: float = Field(gt=0)
    retry_attempts: int = Field(ge=0)
    retry_delay_seconds: float = Field(ge=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Contrato 1.7.0, opcional: el mismo valor que PDF_MAX_SIZE_MB de validación. Acá
    # solo sirve para cortar un body demasiado grande antes de leerlo entero; la
    # regla del tamaño la aplica validacion-pdf.
    pdf_max_size_mb: int = Field(default=5, gt=0)

    @field_validator("consul_service_tags", mode="before")
    @classmethod
    def decode_tags(cls, value: object) -> object:
        return json.loads(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_resolution_configuration(self) -> "Settings":
        fixed_urls = (
            "validacion_url",
            "extraccion_url",
            "persistencia_consultas_url",
            "persistencia_actualizaciones_url",
        )
        if self.consul_enabled:
            if self.consul_http_token_file is None:
                raise ValueError("CONSUL_HTTP_TOKEN_FILE es obligatorio")
            if self.consul_fallback_enabled and any(
                getattr(self, name) is None for name in fixed_urls
            ):
                raise ValueError("el fallback de Consul requiere todas las URLs fijas")
            return self

        missing = [name for name in fixed_urls if getattr(self, name) is None]
        if missing:
            raise ValueError(
                "las URLs fijas son obligatorias cuando Consul está deshabilitado"
            )
        return self


def cargar_settings(transport: httpx.BaseTransport | None = None) -> Settings:
    """Contrato 1.6.0: con CONSUL_ENABLED, la configuración sale del KV de Consul
    (config/orquestador/) y tiene prioridad sobre el entorno."""
    conexion = ConexionConsul()
    if not conexion.consul_enabled:
        return Settings()
    if conexion.consul_http_token_file is None:
        raise ValueError("CONSUL_HTTP_TOKEN_FILE es obligatorio")
    valores = leer_config_de_consul(
        conexion.consul_http_addr,
        conexion.consul_http_token_file,
        "orquestador",
        transport,
    )
    return Settings(**valores)
