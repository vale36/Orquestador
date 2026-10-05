from app.clients.extraction_client import ExtractionHttpClient
from app.clients.persistence_updates_client import PersistenceUpdatesHttpClient
from app.clients.validation_client import ValidationHttpClient
from app.services.orchestrator import OrchestratorService


def get_orchestrator_service() -> OrchestratorService:
    return OrchestratorService(
        validation_service=ValidationHttpClient(),
        extraction_service=ExtractionHttpClient(),
        persistence_service=PersistenceUpdatesHttpClient(),
    )
