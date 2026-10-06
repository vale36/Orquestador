"""Único lugar donde se eligen las implementaciones concretas."""

from functools import lru_cache

import httpx
from fastapi import Request

from app.core.config import Settings
from app.core.extraction_client import ExtractionHttpClient
from app.core.json_http_client import JsonHttpClient
from app.core.persistence_queries_client import PersistenceQueriesHttpClient
from app.core.persistence_updates_client import PersistenceUpdatesHttpClient
from app.core.validation_client import ValidationHttpClient
from app.services.orchestrator import OrchestratorService


@lru_cache
def get_settings() -> Settings:
    return Settings()


def build_orchestrator(
    settings: Settings, http: httpx.AsyncClient
) -> OrchestratorService:
    def client(base_url: str, service_name: str) -> JsonHttpClient:
        return JsonHttpClient(
            http,
            base_url=base_url,
            service_name=service_name,
            retry_attempts=settings.retry_attempts,
            retry_delay_seconds=settings.retry_delay_seconds,
        )

    return OrchestratorService(
        validation_service=ValidationHttpClient(
            client(settings.validacion_url, "validacion-pdf")
        ),
        extraction_service=ExtractionHttpClient(
            client(settings.extraccion_url, "extraccion-texto")
        ),
        persistence_updates=PersistenceUpdatesHttpClient(
            client(
                settings.persistencia_actualizaciones_url,
                "persistencia-actualizaciones",
            )
        ),
        persistence_queries=PersistenceQueriesHttpClient(
            client(settings.persistencia_consultas_url, "persistencia-consultas")
        ),
    )


def get_orchestrator_service(request: Request) -> OrchestratorService:
    """El servicio se arma en el lifespan; los tests lo sustituyen con
    app.dependency_overrides."""
    return request.app.state.orchestrator_service
