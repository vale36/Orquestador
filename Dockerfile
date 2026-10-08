FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock README.md ./
COPY app ./app

RUN uv sync --locked --no-dev

FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PORT=8000 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --no-create-home app

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --chown=app:app logging.json ./
COPY --chown=app:app app ./app

USER app:app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/health\", timeout=2)"]

# --no-access-log: el acceso lo registra la app con el correlation_id.
# exec: uvicorn reemplaza al shell y es el PID 1, así recibe el SIGTERM de docker stop.
# Con --timeout-graceful-shutdown deja de aceptar conexiones y espera hasta 30 s a que
# terminen las requests en curso antes de salir (contrato 1.2.0, 12-Factor IX).
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --no-access-log --timeout-graceful-shutdown 30"]
