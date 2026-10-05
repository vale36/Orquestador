# Orquestador

Microservicio **Orquestador** del proyecto "De Monolito a Microservicios (PDF
Extractext)", implementado en Python con FastAPI y alineado con los schemas de
contrato PDF compartido versión 1.0.0.

El Orquestador recibe un PDF codificado en Base64 como JSON y coordina los
microservicios de validación, extracción y persistencia. No tiene base de datos
propia, no utiliza `pypdf` y no contiene la lógica de esos microservicios.

## Requisitos

- Python 3.11 o superior.
- [`uv`](https://docs.astral.sh/uv/) para instalar y ejecutar el entorno.
- Acceso a los microservicios de validación, extracción y persistencia de
  actualizaciones para procesar `POST /pdf`.

`GET /health` no requiere que las dependencias externas estén disponibles ni
que sus URLs estén configuradas.

## Instalación desde un clon limpio

Clonar el repositorio y entrar al directorio del Orquestador:

```sh
git clone <url-del-repositorio>
cd Orquestador
```

Sincronizar el entorno usando las versiones fijadas en `uv.lock`:

```sh
uv sync --locked
```

## Configuración

Los clientes HTTP leen su configuración del entorno al crear el servicio. Para
ejecutar `POST /pdf` se deben definir estas variables:

| Variable | Uso |
| --- | --- |
| `VALIDACION_URL` | URL base del microservicio de validación. El cliente agrega `POST /validar`. |
| `EXTRACCION_URL` | URL base del microservicio de extracción. El cliente agrega `POST /extraer`. |
| `PERSISTENCIA_ACTUALIZACIONES_URL` | URL base del servicio de persistencia de actualizaciones. El cliente agrega `POST /pdf`. |
| `REQUEST_TIMEOUT_SECONDS` | Timeout positivo y finito en segundos para cada intento HTTP. |
| `RETRY_ATTEMPTS` | Cantidad de reintentos adicionales al primer intento; entero no negativo. |
| `RETRY_DELAY_SECONDS` | Demora finita y no negativa entre reintentos, en segundos. |

Las tres variables de URL son bases sin la ruta de operación indicada. No hay
una URL de persistencia de consultas utilizada por el flujo actual.

El archivo `.env.example` muestra las variables de configuración, pero hay que
completar las URLs y valores de timeout/retry con los del entorno de ejecución.
Para desarrollo local se puede copiar como `.env` y pasar ese archivo a `uv`:

```powershell
Copy-Item .env.example .env
# Editar .env con los valores del entorno
```

No guardar credenciales ni secretos en el repositorio. El archivo `.env` real
debe permanecer local y no debe incluirse en imágenes Docker.

## Ejecución local

Con las variables de entorno configuradas, arrancar Uvicorn desde la raíz:

```powershell
uv run --env-file .env uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

La aplicación queda disponible en `http://localhost:8000`. Para ejecutarla sin
archivo `.env`, se pueden exportar las mismas variables en el entorno de la
terminal y omitir `--env-file .env`.

## Tests

Ejecutar la suite completa desde la raíz del repositorio:

```sh
uv run --with pytest python -m pytest
```

`pytest` no forma parte de las dependencias de runtime declaradas en
`pyproject.toml`; `uv run --with pytest` lo proporciona para esa ejecución sin
agregarlo a las dependencias de producción. Los tests de integración usan la
app real y dobles de los ports. Los tests de clientes sustituyen el transporte
HTTP: no requieren microservicios, MongoDB ni Redis reales.

## Endpoints

### `POST /pdf`

Recibe JSON con `archivo_base64` y `nombre`:

```json
{
  "archivo_base64": "JVBERi0xLjQK...",
  "nombre": "contrato.pdf"
}
```

Si se envía `X-Correlation-ID`, debe ser un UUID válido; ese mismo UUID se
propaga a los clientes y se devuelve en el header de respuesta. Si se omite, el
Orquestador genera un UUID v4.

Ante éxito, responde `201 Created` con el documento devuelto por persistencia:

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

Los valores son ilustrativos. Los campos y tipos están definidos por
`PdfDocumentResponseSchema`; las fechas deben ser ISO-8601 en UTC.
El `id` pertenece al documento creado y lo devuelve persistencia.

Los errores usan el formato común `{"error": {...}}`, con `code`, `message`,
`details` y `correlation_id`. Los status implementados son:

| HTTP | Caso |
| --- | --- |
| `422` | Request inválido o rechazo del microservicio de validación. |
| `502` | Error del microservicio de extracción o persistencia. |
| `503` | Dependencia no disponible, por ejemplo tras agotar reintentos o un timeout. |

Para errores de validación del request, el código es
`REQUEST_VALIDATION_ERROR`. Los códigos de errores recibidos de dependencias se
propagan según el contrato que devuelvan.

### `GET /health`

Responde `200 OK` con `{"status": "ok"}` cuando la aplicación está funcionando.
No consulta bases de datos ni llama a los otros microservicios.

## Dependencias y flujo

La arquitectura separa la entrada HTTP, la coordinación del caso de uso y las
integraciones externas:

```text
FastAPI controller -> OrchestratorService -> service ports -> HTTP clients
                         schemas compartidos entre capas
```

El controller no lleva la lógica de coordinación. `OrchestratorService`
depende de interfaces (`ValidationPort`, `ExtractionPort` y
`PersistenceUpdatesPort`); la factoría inyecta los clientes HTTP concretos.
Esta separación permite probar el flujo con dobles de los ports sin efectuar
llamadas de red.

El Orquestador se comunica mediante clientes HTTP con:

| Microservicio | Configuración | Operación utilizada |
| --- | --- | --- |
| Validación | `VALIDACION_URL` | `POST /validar` |
| Extracción | `EXTRACCION_URL` | `POST /extraer` |
| Persistencia de actualizaciones | `PERSISTENCIA_ACTUALIZACIONES_URL` | `POST /pdf` |

El flujo de `POST /pdf` es:

1. El controller valida la forma del JSON mediante `PdfRequestSchema`, obtiene
   o genera el correlation ID e invoca `OrchestratorService`.
2. El Orchestrator solicita la validación del request.
3. Si la validación es exitosa, solicita extracción de texto y checksum.
4. Con el resultado de extracción, construye la solicitud de creación y la
   envía a persistencia.
5. Devuelve al consumidor la respuesta de persistencia.

Si falla validación, no se llama a extracción ni persistencia. Si falla
extracción, no se llama a persistencia. El controller maneja HTTP; la
coordinación pertenece al servicio y los puertos desacoplan al servicio de sus
clientes concretos. El Orquestador no consulta una base de datos propia.

## Timeout y retry

Los clientes HTTP reutilizan `REQUEST_TIMEOUT_SECONDS`,
`RETRY_ATTEMPTS` y `RETRY_DELAY_SECONDS` para cada operación. El número de
intentos totales es el intento inicial más la cantidad configurada de
reintentos. El cliente reintenta timeouts, errores de conexión y respuestas
HTTP `408`, `429`, `500`, `502`, `503` o `504`; los demás errores HTTP no son
reintentables por esta política.

## Compensación SAGA

Si la creación en persistencia falla después de una validación y extracción
exitosas, `OrchestratorService` intenta
`PersistenceUpdatesPort.compensate(checksum, correlation_id)`. Usa el checksum
de extracción y el mismo correlation ID del flujo. No compensa ante fallos de
validación o extracción ni cuando la creación termina correctamente. El
contrato del port requiere que la compensación repetida sea segura y tolere que
el recurso ya no exista.

**Limitación de la integración actual:** `PersistenceUpdatesHttpClient`
implementa la creación, pero todavía no implementa `compensate()`. Este
repositorio tampoco documenta una ruta HTTP contractual para esa operación.
Por eso la orquestación intenta la llamada del port y registra el error si no
se puede ejecutar; el error original de persistencia sigue siendo el principal.
No se debe asumir que la compensación remota está operativa ni inventar una
ruta hasta que exista un contrato acordado con el servicio de persistencia.

## Decisiones técnicas y deudas conocidas

- FastAPI expone los endpoints; Pydantic define los schemas; `OrchestratorService`
  depende de ports y los clientes HTTP implementan las comunicaciones externas.
- La configuración de dependencias se resuelve mediante
  `get_orchestrator_service`; no se agrega persistencia local ni lógica de PDF.
- El retry está acotado y parametrizado por entorno. Los tests comprueban
  timeout/retry y los flujos con dobles, sin requerir servicios externos.
- La integración del método `compensate()` en el cliente HTTP queda pendiente
  hasta definir su contrato externo.
- `.env.example` incluye `PERSISTENCIA_CONSULTAS_URL`, pero el código actual no
  utiliza esa variable: no es necesaria para este flujo.
- `pytest` no está declarado como dependencia de desarrollo; los comandos de
  tests lo resuelven de forma efímera mediante `uv run --with pytest`.

## Docker

La imagen usa las dependencias fijadas, escucha en el puerto `8000` por defecto,
permite cambiarlo mediante `PORT` y ejecuta la aplicación con un usuario sin
privilegios. Consultar [docs/DOCKER.md](docs/DOCKER.md) para build, ejecución,
healthcheck y configuración en contenedor.

## Estructura relevante

```text
app/
├── main.py
├── clients/       # Clientes HTTP y política compartida de timeout/retry
├── controllers/   # Endpoints FastAPI
├── schemas/       # Contratos de request, response y errores
└── services/      # Orquestación, ports y composición de dependencias
tests/
├── integration/
└── unit/
```
