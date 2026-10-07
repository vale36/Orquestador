"""Configuration entry point for the orchestrator service."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables del contrato. Obligatorias salvo LOG_LEVEL: si falta una, la app no
    arranca."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    validacion_url: str
    extraccion_url: str
    persistencia_consultas_url: str
    persistencia_actualizaciones_url: str
    request_timeout_seconds: float = Field(gt=0)
    retry_attempts: int = Field(ge=0)
    retry_delay_seconds: float = Field(ge=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
