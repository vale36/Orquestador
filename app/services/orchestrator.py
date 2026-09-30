from typing import Any

from app.services.ports import (
    ExtractionPort,
    PersistenceUpdatesPort,
    ValidationPort,
)


class OrchestratorService:
    def __init__(
        self,
        validation_service: ValidationPort,
        extraction_service: ExtractionPort,
        persistence_service: PersistenceUpdatesPort,
        compensation_service: Any,
    ) -> None:
        self._validation_service = validation_service
        self._extraction_service = extraction_service
        self._persistence_service = persistence_service
        self._compensation_service = compensation_service

    def orchestrate(
        self,
        request: dict[str, Any],
        correlation_id: str,
    ) -> Any:
        self._validation_service.validate(request, correlation_id)
        self._extraction_service.extract(request, correlation_id)

        try:
            return self._persistence_service.create(request, correlation_id)
        except Exception:
            self._compensation_service.compensate(request, correlation_id)
            raise
