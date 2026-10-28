"""Configuration entry point for the orchestrator service."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables del contrato. Obligatorias salvo LOG_LEVEL: si falta una, la app no
    arranca."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    validacion_url: str | None = None
    extraccion_url: str | None = None
    persistencia_consultas_url: str | None = None
    persistencia_actualizaciones_url: str | None = None
    consul_enabled: bool = False
    consul_http_addr: str = "http://consul:8500"
    consul_http_token_file: Path | None = None
    consul_fallback_enabled: bool = False
    request_timeout_seconds: float = Field(gt=0)
    retry_attempts: int = Field(ge=0)
    retry_delay_seconds: float = Field(ge=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

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
