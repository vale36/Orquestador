# Orquestador

Microservicio **Orquestador** del proyecto "De Monolito a Microservicios (PDF
Extractext)", implementado en Python con FastAPI y alineado con el contrato
compartido `microservicios-pdf` v1.0.0.

El Orquestador recibe un PDF codificado en Base64 como JSON y coordina los
microservicios de validación, extracción y persistencia. No tiene base de datos
propia, no utiliza `pypdf` ni Redis y no contiene la lógica de esos
microservicios.

## Requisitos

- Python 3.11 o superior.
- [`uv`](https://docs.astral.sh/uv/) para instalar y ejecutar el entorno.
- Acceso a los microservicios de validación, extracción y persistencia
  (actualizaciones y consultas) para procesar `POST /pdf`.

## Instalación desde un clon limpio

```sh
git clone <url-del-repositorio>
cd Orquestador
uv sync --locked
```

## Configuración

Todas las variables son obligatorias y se validan al arrancar con
`pydantic-settings`: si falta alguna o tiene un valor inválido, la aplicación
no inicia.

| Variable | Uso |
| --- | --- |
| `VALIDACION_URL` | URL base de `validacion-pdf` (`POST /validar`). |
| `EXTRACCION_URL` | URL base de `extraccion-texto` (`POST /extraer`). |
| `PERSISTENCIA_ACTUALIZACIONES_URL` | URL base de `persistencia-actualizaciones` (`POST /pdf`, `DELETE /pdf/{id}`). |
| `PERSISTENCIA_CONSULTAS_URL` | URL base de `persistencia-consultas` (`GET /pdf/checksum/{checksum}`, para la compensación SAGA). |
| `REQUEST_TIMEOUT_SECONDS` | Timeout de cada llamada, mayor que cero. |
| `RETRY_ATTEMPTS` | Reintentos además del primer intento; entero no negativo. |
| `RETRY_DELAY_SECONDS` | Demora entre reintentos, no negativa. |

`.env.example` tiene todas las claves sin valores. Para desarrollo local:

```powershell
Copy-Item .env.example .env
# Completar .env con los valores del entorno
```

El archivo `.env` real queda local: está en `.gitignore` y en `.dockerignore`.

## Ejecución local

```powershell
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

La aplicación lee `.env` si existe; también se pueden exportar las variables en
la terminal.

## Endpoints

### `POST /pdf`

Recibe JSON con `archivo_base64` y `nombre`:

```json
{
  "archivo_base64": "JVBERi0xLjQK...",
  "nombre": "contrato.pdf"
}
```

Ante éxito responde `201 Created` con el documento devuelto por persistencia:

```json
{
  "id": "8f6f7c3e-12d5-4f57-9c6c-123456789abc",
  "nombre": "contrato.pdf",
  "checksum": "checksum",
  "texto": "Texto extraído por el microservicio de extracción",
  "tamano_bytes": 1024,
  "paginas": 1,
  "created_at": "2026-01-01T00:00:00Z",
  "updated_at": "2026-01-01T00:00:00Z"
}
```

Los errores usan el formato común `{"error": {"code", "message", "details",
"correlation_id"}}`. El status HTTP sale del código, según la tabla del
contrato, así el error de una dependencia llega al cliente con el mismo
significado:

| Código | HTTP | Ejemplo |
| --- | --- | --- |
| `VALIDATION_ERROR` | `400` | Falta `archivo_base64` o `nombre`. |
| `PDF_TOO_LARGE` | `413` | Lo rechazó validación. |
| `PDF_INVALID`, `PDF_CORRUPTED` | `422` | Lo rechazó validación o extracción. |
| `DUPLICATE_CHECKSUM` | `409` | El PDF ya estaba guardado. |
| `DEPENDENCY_UNAVAILABLE` | `503` | Una dependencia no respondió (timeout, conexión) o respondió fuera del contrato. |
| `DATABASE_ERROR` | `503` | La base de persistencia no responde. |
| `INTERNAL_ERROR` | `500` | Error no previsto. |

Los errores de validación del request no incluyen el valor recibido, para no
devolver ni registrar el PDF en Base64.

### `GET /health`

Responde `200 OK` con `{"status": "ok"}`. No llama a los otros microservicios.

### Correlation ID

Un middleware fija el `X-Correlation-ID` de cada request: si llega un UUID lo
reutiliza; si falta o no es un UUID, genera uno nuevo (el contrato identifica
con UUID). Se envía a cada dependencia, se devuelve en todas las respuestas
(incluido `/health`) y aparece en el cuerpo de los errores.

## Arquitectura

```text
app/
├── main.py                        # lifespan, middleware, errores, logs
├── controllers/pdf_routes.py      # POST /pdf
├── schemas/pdf_schemas.py         # contrato HTTP público (Pydantic)
├── services/
│   ├── orchestrator.py            # flujo y compensación SAGA
│   └── ports.py                   # puertos ABC async hacia las dependencias
├── models/pdf_document.py         # PdfRequest, ExtractionResult, PdfDocument
└── core/
    ├── composition.py             # único lugar donde se arman los adaptadores
    ├── config.py                  # Settings (pydantic-settings)
    ├── json_http_client.py        # httpx async: timeout, reintentos, errores
    ├── validation_client.py       # adaptadores que implementan los puertos
    ├── extraction_client.py
    ├── persistence_updates_client.py
    ├── persistence_queries_client.py
    ├── document_mapping.py        # JSON del contrato ↔ modelos de dominio
    ├── exceptions.py
    └── logs.py
```

Flujo de dependencias: `controller → OrchestratorService → puertos ← adaptadores
httpx`. El service no importa FastAPI, httpx ni los schemas Pydantic: trabaja
con los modelos de dominio. El lifespan crea un único `httpx.AsyncClient` con
`REQUEST_TIMEOUT_SECONDS` y lo cierra al apagar.

Flujo de `POST /pdf`:

1. Validar el PDF (`validacion-pdf`).
2. Extraer texto, páginas y checksum (`extraccion-texto`).
3. Crear el documento (`persistencia-actualizaciones`).
4. Devolver el documento creado.

Si falla la validación no se llama a extracción; si falla la extracción no se
llama a persistencia.

**Async de punta a punta.** El endpoint y los adaptadores son async: mientras
espera a una dependencia, el orquestador no ocupa un hilo y puede atender
otras requests.

## Timeout y retry

Cada llamada usa `REQUEST_TIMEOUT_SECONDS`. Las operaciones idempotentes
(validar, extraer, consultar por checksum, borrar) se reintentan
`RETRY_ATTEMPTS` veces, con `RETRY_DELAY_SECONDS` entre intentos
(`asyncio.sleep`, sin bloquear), ante timeouts, errores de conexión y
respuestas `408`, `429`, `500`, `502`, `503` o `504`.

El alta en persistencia (`POST /pdf`) **no se reintenta**: si el primer intento
se guardó pero la respuesta se perdió, un reintento recibiría `409`. Ese caso
lo resuelve la compensación SAGA.

El cortocircuito (circuit breaker) no se programa: lo aplica Traefik.

## Compensación SAGA

Se compensa **solo cuando el resultado del alta es incierto**: persistencia no
respondió (timeout, conexión caída o respuesta inválida). En ese caso el
documento pudo haberse guardado aunque la respuesta no llegó.

La compensación:

1. Busca el checksum en `persistencia-consultas`.
2. Si el documento existe y su `created_at` es posterior al inicio de esta
   request, lo borra con `DELETE /pdf/{id}` en `persistencia-actualizaciones`.
3. Si no existe, o ya existía desde antes, no hace nada.

Es **idempotente** (un `404` al borrar también es éxito) y queda **registrada
en los logs** con su resultado (`deleted`, `nothing-to-undo` o `failed`). Si la
compensación falla, se registra y el cliente recibe el error original del alta.

**No se compensa** ante un error del contrato de persistencia (`409`, `400`,
`422`): significa que no se guardó nada. Ante un `409`, borrar por checksum
eliminaría el documento que ya existía.

## Logs

Van a `stdout`, sin archivos, y cada línea lleva el `correlation_id`: el
middleware lo guarda en una `ContextVar` y una *record factory* lo agrega a
cada registro, así lo tienen también los logs de la SAGA y de los reintentos.

```text
2026-10-06 20:30:01,905 INFO app.main correlation_id=8f6f7c3e-... method=POST path=/pdf status=201 duracion_ms=48.2
2026-10-06 20:30:02,114 WARNING app.core.json_http_client correlation_id=1b2c... reintentando POST /extraer en extraccion-texto intento=2 de 3 motivo=ReadTimeout
```

El access log de uvicorn está desactivado en la imagen porque no lleva el
`correlation_id`.

## Tests y calidad

```sh
uv run pytest
uv run ruff check app tests
uv run black --check app tests
```

La suite es hermética: no necesita los otros microservicios ni `.env`
(`tests/conftest.py` fija la configuración e ignora el `.env` local).

- **Servicio:** flujo, orden de las llamadas, corte ante errores y cada caso de
  la SAGA, con dobles de los puertos (`tests/doubles.py`).
- **Adaptadores:** rutas, cuerpos, `X-Correlation-ID`, reintentos, no
  reintento del alta, `404` esperados y respuestas fuera del contrato, con
  `httpx.MockTransport` inyectado.
- **API:** la app real con los dobles inyectados por `app.dependency_overrides`:
  respuesta del contrato, cada código de error, correlation ID, logs, y un
  flujo completo con los adaptadores reales y un transporte HTTP de prueba
  (incluido un reintento).

Queda fuera a propósito: la integración contra los servicios reales, que se
prueba en el repositorio de integración con Docker Compose.

## Docker

Ver [docs/DOCKER.md](docs/DOCKER.md).

## Deuda técnica

- **Historial de TDD.** La primera entrega implementó el service antes que sus
  tests y trajo la mayoría de los `feat` con código y tests juntos. Desde los
  arreglos de la auditoría (rama `fix/auditoria-orquestador`), cada cambio de
  comportamiento sigue rojo → verde.
- **Margen de la SAGA.** "Creado durante esta request" se decide comparando
  `created_at` con el inicio de la request, al segundo. Si persistencia y el
  orquestador corren con relojes muy desincronizados, la comparación puede
  fallar; en Docker Compose comparten el reloj del host.
