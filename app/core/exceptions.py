"""Errores de las dependencias, con el código del contrato común de errores."""


class ExternalServiceError(Exception):
    """Una dependencia respondió un error con el formato común del contrato."""

    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class DependencyUnavailableError(ExternalServiceError):
    """La dependencia no respondió, no se pudo conectar o respondió algo inválido."""

    def __init__(self, message: str) -> None:
        super().__init__("DEPENDENCY_UNAVAILABLE", message)
