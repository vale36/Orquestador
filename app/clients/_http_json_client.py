import json
import os
import socket
import urllib.error
import urllib.request
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.pdf_schemas import ServiceErrorSchema
from app.services.ports import (
    DependencyUnavailableError,
    ExternalServiceError,
)

ResponseSchema = TypeVar("ResponseSchema", bound=BaseModel)
ServiceError = TypeVar("ServiceError", bound=ExternalServiceError)


class HttpJsonClient:
    def __init__(
        self,
        url_environment_variable: str,
        service_name: str,
    ) -> None:
        self._base_url = self._required_environment_value(
            url_environment_variable
        ).rstrip("/")
        timeout_value = self._required_environment_value(
            "REQUEST_TIMEOUT_SECONDS"
        )
        try:
            self._timeout_seconds = float(timeout_value)
        except ValueError as error:
            raise ValueError(
                "REQUEST_TIMEOUT_SECONDS must be a number"
            ) from error
        if self._timeout_seconds <= 0:
            raise ValueError("REQUEST_TIMEOUT_SECONDS must be greater than zero")
        self._service_name = service_name

    @staticmethod
    def _required_environment_value(name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise ValueError(f"{name} must be configured")
        return value

    def post_json(
        self,
        path: str,
        payload: dict[str, object],
        correlation_id: str,
        response_schema: type[ResponseSchema],
        error_schema: type[ServiceError],
    ) -> ResponseSchema:
        request = urllib.request.Request(
            url=f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Correlation-ID": correlation_id,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self._timeout_seconds,
            ) as response:
                response_body = response.read()
        except urllib.error.HTTPError as error:
            self._raise_http_error(error, error_schema, correlation_id)
        except urllib.error.URLError as error:
            if isinstance(error.reason, (TimeoutError, socket.timeout)):
                self._raise_timeout(correlation_id, error)
            self._raise_unavailable(correlation_id, str(error.reason))
        except (TimeoutError, socket.timeout) as error:
            self._raise_timeout(correlation_id, error)
        except OSError as error:
            self._raise_unavailable(correlation_id, str(error))

        try:
            return response_schema.model_validate_json(response_body)
        except (ValueError, ValidationError) as error:
            self._raise_unavailable(
                correlation_id,
                f"Invalid response from {self._service_name}: {error}"
            )

    def _raise_http_error(
        self,
        error: urllib.error.HTTPError,
        error_schema: type[ServiceError],
        correlation_id: str,
    ) -> None:
        try:
            payload = json.loads(error.read())
            error_payload = payload["error"]
            service_error = ServiceErrorSchema.model_validate(error_payload)
        except (KeyError, TypeError, ValueError, ValidationError) as parse_error:
            self._raise_unavailable(
                correlation_id,
                f"{self._service_name} returned HTTP {error.code} with "
                f"an invalid error response: {parse_error}"
            )

        raise error_schema(service_error) from error

    def _raise_timeout(
        self,
        correlation_id: str,
        cause: BaseException,
    ) -> None:
        self._raise_unavailable(
            correlation_id,
            f"Request to {self._service_name} timed out",
            cause=cause,
        )

    def _raise_unavailable(
        self,
        correlation_id: str,
        message: str,
        cause: BaseException | None = None,
    ) -> None:
        service_error = ServiceErrorSchema(
            code="DEPENDENCY_UNAVAILABLE",
            message=message,
            details={},
            correlation_id=correlation_id,
        )
        error = DependencyUnavailableError(service_error)
        if cause is not None:
            raise error from cause
        raise error
