"""Adaptador HTTP async (httpx) hacia los otros microservicios."""

import asyncio
import logging

import httpx

from app.core.exceptions import DependencyUnavailableError, ExternalServiceError

logger = logging.getLogger(__name__)

RETRYABLE_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}


class JsonHttpClient:
    """Envía JSON con X-Correlation-ID, reintenta lo transitorio y traduce los
    errores al formato común del contrato. El timeout lo fija el AsyncClient."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        service_name: str,
        retry_attempts: int,
        retry_delay_seconds: float,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._service_name = service_name
        self._retry_attempts = retry_attempts
        self._retry_delay_seconds = retry_delay_seconds

    async def request(
        self,
        method: str,
        path: str,
        correlation_id: str,
        *,
        json: dict | None = None,
        retry: bool = True,
        not_found_ok: bool = False,
    ) -> dict | None:
        """Devuelve el cuerpo JSON, o None ante 204 (o 404 si not_found_ok).
        retry=False para operaciones que no son idempotentes."""
        body, _ = await self.request_with_headers(
            method,
            path,
            correlation_id,
            json=json,
            retry=retry,
            not_found_ok=not_found_ok,
        )
        return body

    async def request_with_headers(
        self,
        method: str,
        path: str,
        correlation_id: str,
        *,
        json: dict | None = None,
        retry: bool = True,
        not_found_ok: bool = False,
    ) -> tuple[dict | None, httpx.Headers]:
        """Como request, pero también devuelve los headers de la respuesta."""
        response = await self._send(method, path, correlation_id, json, retry)
        if response.status_code == 204 or (
            not_found_ok and response.status_code == 404
        ):
            return None, response.headers
        if response.is_success:
            return self._json(response), response.headers
        raise self._error_from(response)

    async def _send(
        self,
        method: str,
        path: str,
        correlation_id: str,
        json: dict | None,
        retry: bool,
    ) -> httpx.Response:
        attempts = self._retry_attempts + 1 if retry else 1
        for attempt in range(1, attempts + 1):
            last = attempt == attempts
            try:
                response = await self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json,
                    headers={"X-Correlation-ID": correlation_id},
                )
            except httpx.TransportError as error:
                if last:
                    raise DependencyUnavailableError(
                        f"{self._service_name} no responde"
                    ) from error
                reason = type(error).__name__
            else:
                if last or response.status_code not in RETRYABLE_HTTP_STATUSES:
                    return response
                reason = f"HTTP {response.status_code}"
            logger.warning(
                "reintentando %s %s en %s intento=%d de %d motivo=%s",
                method,
                path,
                self._service_name,
                attempt + 1,
                attempts,
                reason,
            )
            await asyncio.sleep(self._retry_delay_seconds)
        raise AssertionError("el bucle de reintentos siempre retorna o lanza")

    def _json(self, response: httpx.Response) -> dict:
        try:
            return response.json()
        except ValueError as error:
            raise DependencyUnavailableError(
                f"{self._service_name} respondió un cuerpo que no es JSON"
            ) from error

    def _error_from(self, response: httpx.Response) -> ExternalServiceError:
        try:
            error = response.json()["error"]
            return ExternalServiceError(
                error["code"], error["message"], error.get("details", {})
            )
        except (ValueError, KeyError, TypeError):
            return DependencyUnavailableError(
                f"{self._service_name} respondió HTTP {response.status_code} "
                "sin el formato común de errores"
            )
