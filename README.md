# Orquestador

Microservicio **Orquestador** del proyecto "De Monolito a Microservicios (PDF
Extractext)", implementado en Python con FastAPI y alineado con el contrato
compartido `microservicios-pdf` v1.4.0 (en el repo
[integracion](https://github.com/Enzo-Ezequiel/integracion), `CONTRATO.md`).

El Orquestador recibe un PDF codificado en Base64 como JSON y coordina los
microservicios de validación, extracción y persistencia. No tiene base de datos
propia, no lee PDFs, no usa MongoDB ni Redis y no contiene la lógica de esos
microservicios.

## Cómo ejecutar todo el sistema

El orquestador solo no hace nada útil: necesita a los otros cuatro servicios, MongoDB,
Redis y Traefik. Todo eso se levanta junto con **un solo script** del repo `integracion`.
Esta guía es para una máquina con Windows; en Linux o Mac los comandos son los mismos.

### 1. Instalar las herramientas (una sola vez)

| Herramienta | Para qué | Cómo saber si ya está |
|---|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Corre todos los servicios en contenedores | `docker --version` |
| [Git](https://git-scm.com/) (trae **Git Bash**) | Bajar los repos y correr el script | `git --version` |
| [uv](https://docs.astral.sh/uv/) | Lo pide el script; también corre los tests y genera PDFs de prueba | `uv --version` |

Docker Desktop tiene que estar **abierto** (el ícono de la ballena quieto) antes de seguir.

### 2. Armar la carpeta del proyecto (una sola vez)

Todos los repos van uno al lado del otro, dentro de una misma carpeta. La infraestructura
se clona con el nombre `dockers`:

```text
Proyecto Microservicios/
├── dockers/                        ← infraestructura: Consul, Traefik, MongoDB y Redis
├── integracion/                    ← los cinco microservicios juntos
├── Orquestador/
├── validacion-pdf/
├── Extraccion-de-texto-pdf-/
├── persistencia-actualizaciones/
└── persistencia-consultas/
```

Desde esa carpeta, en **Git Bash**:

```bash
git clone https://github.com/vale36/infraestructura.git dockers
git clone https://github.com/Enzo-Ezequiel/integracion.git
git clone https://github.com/vale36/Orquestador.git
git clone https://github.com/valentinapenasco/validacion-pdf.git
git clone https://github.com/NicolasPerez735/Extraccion-de-texto-pdf-.git
git clone https://github.com/matiasscanoo/persistencia-actualizaciones.git
git clone https://github.com/ManuelGomez33/persistencia-consultas.git
```

Faltan los certificados HTTPS de Traefik, que no se suben a GitHub porque `key.pem` es una
clave privada. Copiá `cert.pem` y `key.pem` de un compañero a `dockers/traefik/certs/`, o
generalos con [mkcert](https://github.com/FiloSottile/mkcert) (ver el README de
`integracion`). Para que el navegador confíe en el certificado, corré una vez
`mkcert -install`.

### 3. Levantar todo: dos docker compose, en orden

Primero la infraestructura y después los microservicios. En **Git Bash**:

```bash
docker network create redutn          # una sola vez
cd dockers
docker compose up -d --wait           # 1.º Consul, Traefik, MongoDB y Redis
cd ../integracion
./scripts/levantar.sh                 # 2.º los cinco microservicios
```

El primer compose arranca Consul, crea sus permisos (ACL) y los tokens que usan los
servicios, y después Traefik, MongoDB y Redis. El script del segundo revisa que la
infraestructura esté sana, construye las cinco imágenes, las levanta (cada servicio se
registra solo en Consul) y prueba que respondan. La primera vez tarda unos minutos (baja
imágenes); termina con `Listo: https://pdf.universidad.localhost`.

### 4. Probarlo

- **En el navegador:** <https://pdf.universidad.localhost/docs> abre Swagger, la página con
  los endpoints del orquestador. <https://pdf.universidad.localhost/health> tiene que decir
  `{"status":"ok"}`.
- **Subir un PDF de verdad**, en PowerShell (cambiá la ruta por un PDF tuyo):

  ```powershell
  $pdf = "C:\ruta\a\un\archivo.pdf"
  $body = @{
    archivo_base64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($pdf))
    nombre = Split-Path $pdf -Leaf
  } | ConvertTo-Json
  Invoke-RestMethod -Method Post -Uri https://pdf.universidad.localhost/pdf `
    -ContentType "application/json" -Body $body
  ```

  La respuesta es el documento guardado: `id`, `checksum`, `texto`, `paginas` y fechas. Si
  subís el **mismo** PDF otra vez, la respuesta es `409 DUPLICATE_CHECKSUM`: es lo esperado,
  ya estaba guardado.

- **Ver por dónde pasó un pedido:** cada respuesta trae el header `X-Correlation-ID`.
  Desde `integracion`, `docker compose logs | grep <ese-id>` muestra la línea de cada
  servicio que lo atendió.
- **Ver qué servicios están sanos:** la interfaz de Consul está en
  <http://127.0.0.1:8500/ui/>. Pide un token, que se lee con
  `docker compose exec -T consul cat /consul/data/bootstrap/ui.token` desde
  `dockers/consul`.

### 5. Apagar

En orden inverso, sin perder los documentos guardados:

```bash
cd integracion && docker compose down      # los microservicios (se borran solos de Consul)
cd ../dockers && docker compose down       # la infraestructura (MongoDB conserva los datos)
```

`docker compose down -v` en `dockers` también borra la base de datos y los permisos de
Consul: solo usarlo para empezar de cero.

### Si algo falla

| Síntoma | Qué hacer |
|---|---|
| `Docker no está corriendo` | Abrir Docker Desktop y esperar a que termine de arrancar |
| `falta el repo ../<nombre>` | Clonar ese repo al lado de `integracion` (paso 2) |
| `no existe la red redutn` o `consul no está sano` | Levantar primero la infraestructura (paso 3, `dockers`) |
| `falta el token microservices` | El compose de `dockers` no terminó bien: `docker compose logs consul-bootstrap` en `dockers` |
| El navegador avisa que el sitio no es seguro | Correr `mkcert -install` y reiniciar el navegador |
| Un puerto 80 o 443 ocupado | Cerrar el programa que lo usa (otro servidor web o IIS) |
| `falta uv` o `falta docker` | Instalar esa herramienta (paso 1) y abrir una terminal nueva |
| Un servicio queda `unhealthy` | `docker compose logs <servicio>` muestra el error |

Para correr **solo el orquestador** sin Docker (por ejemplo, para desarrollar o correr sus
tests), seguir las secciones de abajo.

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

Las variables se validan al arrancar con `pydantic-settings`: si falta una
obligatoria o alguna tiene un valor inválido, la aplicación no inicia.

| Variable | Uso |
| --- | --- |
| `VALIDACION_URL` | URL fija usada fuera de Consul o como fallback explícito. |
| `EXTRACCION_URL` | URL fija usada fuera de Consul o como fallback explícito. |
| `PERSISTENCIA_ACTUALIZACIONES_URL` | URL fija usada fuera de Consul o como fallback explícito. |
| `PERSISTENCIA_CONSULTAS_URL` | URL fija usada fuera de Consul o como fallback explícito. |
| `CONSUL_ENABLED` | Habilita Service Discovery. Por defecto es `false`. |
| `CONSUL_HTTP_ADDR` | Dirección HTTP de Consul dentro de Docker, normalmente `http://consul:8500`. |
| `CONSUL_HTTP_TOKEN_FILE` | Archivo con el token ACL del Orquestador. Es obligatorio con Consul habilitado. |
| `CONSUL_FALLBACK_ENABLED` | Permite URLs fijas si falla el descubrimiento. Por defecto es `false`. |
| `REQUEST_TIMEOUT_SECONDS` | Timeout de cada llamada, mayor que cero. |
| `RETRY_ATTEMPTS` | Reintentos además del primer intento; entero no negativo. |
| `RETRY_DELAY_SECONDS` | Demora entre reintentos, no negativa. |
| `LOG_LEVEL` | Opcional (contrato 1.2.0): `DEBUG`, `INFO` (por defecto), `WARNING` o `ERROR`. |

`.env.example` tiene todas las claves sin valores. Para desarrollo local:

```powershell
Copy-Item .env.example .env
# Completar .env con los valores del entorno
```

El archivo `.env` real queda local: está en `.gitignore` y en `.dockerignore`.

### Service Discovery con Consul

Con `CONSUL_ENABLED=true`, el Orquestador consulta
`/v1/health/service/<servicio>?passing=true` y usa solo instancias cuyo health check
esté pasando. Los servicios se identifican como `validacion-pdf`,
`extraccion`, `persistencia-consultas` y `persistencia-actualizaciones`.

El token se lee del archivo indicado por `CONSUL_HTTP_TOKEN_FILE`; no se versiona.
Ejemplo Docker de secreto montado como archivo:

```yaml
volumes:
  - ./secrets/consul_orchestrator_token:/run/secrets/consul_orchestrator_token:ro
environment:
  CONSUL_HTTP_TOKEN_FILE: /run/secrets/consul_orchestrator_token
```

La lista de instancias sanas de cada servicio se guarda **2 segundos**
(`CACHE_SEGUNDOS` en `app/core/consul_service_discovery.py`): cada PDF hace cuatro
llamadas y sin caché serían cuatro consultas más a Consul. Con 5 usuarios en k6 pasó de
61,6 a 81,4 PDF/s. Los errores no se guardan. Entre las réplicas sanas el Orquestador
elige de forma circular en cada llamada; si una falla, el reintento va a la siguiente
(probado matando y colgando réplicas). Las operaciones no idempotentes mantienen un solo
intento.

`CONSUL_FALLBACK_ENABLED=false` es el comportamiento seguro y predeterminado. Si
Consul falla o no hay instancias saludables, se usa `DEPENDENCY_UNAVAILABLE` y no
se envía tráfico a una dirección desconocida. Habilitar el fallback exige definir las
cuatro URLs fijas; debe hacerse solo con esa intención explícita y por el tiempo que
se considere necesario.

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

La respuesta exitosa reenvía el header `X-Extraction-Time-Ms` que informa
`extraccion-texto` (decodificar, leer con PyMuPDF y calcular el checksum). Así las
pruebas de carga, que entran por el orquestador, miden la extracción por separado del
tiempo total de la request. Si extracción no lo informa, el header no se envía. No
forma parte del contrato.

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

Excepción (contrato 1.4.0): un `503` con `details.reason` `cola_llena` o
`espera_agotada` es el backpressure de extracción (servicio saturado) y **no se
reintenta**: un reintento le suma carga a un servicio que ya rechaza por falta de
lugar. Se devuelve enseguida al cliente como `503 DEPENDENCY_UNAVAILABLE` con el
mismo `details`. No hay SAGA: pasa antes del alta.

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

## Logs (12-Factor XI)

Van a `stdout`, sin archivos. La configuración está en [`logging.json`](logging.json),
en la raíz del repo (formato `dictConfig`), y el nivel sale de `LOG_LEVEL`, que se
aplica en el `lifespan` (contrato `microservicios-pdf` 1.2.0). Cada línea lleva el
`correlation_id`: el middleware lo guarda en una `ContextVar` y una *record factory*
lo agrega a cada registro, así lo tienen también los logs de la SAGA y de los
reintentos. Con el mismo id se sigue la request en los logs de los otros servicios.

```text
INFO app.main correlation_id=- servicio iniciado
INFO app.services.orchestrator correlation_id=8f6f7c3e-... validacion aceptada
INFO app.services.orchestrator correlation_id=8f6f7c3e-... texto extraido paginas=10 checksum=9f86d0...
INFO app.services.orchestrator correlation_id=8f6f7c3e-... documento creado id=1111... checksum=9f86d0...
INFO app.main correlation_id=8f6f7c3e-... method=POST path=/pdf status=201 duracion_ms=48.2
WARNING app.core.json_http_client correlation_id=1b2c... reintentando POST /extraer en extraccion-texto intento=2 de 3 motivo=ReadTimeout
```

| Nivel | Qué registra este servicio |
| --- | --- |
| `INFO` | Cada request, cada paso del flujo (validación aceptada, texto extraído, documento creado), compensación completada, inicio y apagado. |
| `WARNING` | Reintentos hacia otro servicio, compensación SAGA iniciada, errores del contrato devueltos al cliente. |
| `ERROR` | Compensación fallida y errores no previstos, con traceback. |

**No se registran** el Base64, el texto extraído ni el nombre del archivo (puede
tener datos personales): el documento se identifica por `id` y `checksum`. Hay un
test que lo verifica. `httpx` queda en `WARNING` para no repetir en cada llamada
lo que ya registra el orquestador, y el access log de uvicorn está desactivado en
la imagen porque lo registra la app.

## Finalización segura (12-Factor IX)

La imagen corre uvicorn como PID 1 (`exec` en el `CMD`) con
`--timeout-graceful-shutdown 30`. Ante `SIGTERM` (`docker stop`) deja de aceptar
conexiones, termina las requests en curso y cierra el cliente httpx en el
`lifespan` (`apagado iniciado` / `apagado completo`); sale con código 0. Probado
con la imagen `1.0.3`.

El peor caso de una request (tres intentos de 10 s hacia una dependencia lenta)
puede pasar los 30 s. Si el plazo se agota o llega un `SIGKILL`, el orquestador no
alcanza a compensar: lo que pudo quedar es un documento completo guardado (cada alta
es una sola escritura), y reenviar el mismo PDF responde `409`.

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
  reintento del alta ni del `503` por backpressure, `404` esperados y respuestas fuera del contrato, con
  `httpx.MockTransport` inyectado.
- **API:** la app real con los dobles inyectados por `app.dependency_overrides`:
  respuesta del contrato, cada código de error, correlation ID, logs, y un
  flujo completo con los adaptadores reales y un transporte HTTP de prueba
  (incluido un reintento).
- **Logs y lifespan:** `LOG_LEVEL` opcional e inválido, formato de
  `logging.json`, eventos de cada paso sin datos sensibles, inicio y apagado en
  el `lifespan` y nivel aplicado al arrancar.

Queda fuera a propósito: la integración contra los servicios reales, que se
prueba en el repositorio de integración con Docker Compose.

## Docker

Ver [docs/DOCKER.md](docs/DOCKER.md). En la integración la imagen es `orquestador:1.0.7`.

La versión del servicio es la de `pyproject.toml` (1.0.7): es la que muestra Swagger en
`/docs` y el tag de la imagen. `tests/integration/test_openapi.py` verifica que
`FastAPI(version=...)` en `app/main.py` coincida con `pyproject.toml`; en una versión
nueva se cambian los dos.

## Deuda técnica

- **Historial de TDD.** La primera entrega implementó el service antes que sus
  tests y trajo la mayoría de los `feat` con código y tests juntos. Desde los
  arreglos de la auditoría (rama `fix/auditoria-orquestador`), cada cambio de
  comportamiento sigue rojo → verde.
- **Margen de la SAGA.** "Creado durante esta request" se decide comparando
  `created_at` con el inicio de la request, al segundo. Si persistencia y el
  orquestador corren con relojes muy desincronizados, la comparación puede
  fallar; en Docker Compose comparten el reloj del host.
- **Un solo proceso.** El orquestador corre en un proceso y es el que pone el techo del
  sistema (~80 PDF/s con 5 usuarios en k6, 2026-10-31). Alcanza de sobra para el
  escenario del profesor (30 pedidos por segundo, 56 ms de promedio); si hiciera falta
  más, se le agregan réplicas detrás de Traefik.
