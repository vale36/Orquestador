# Orquestador

Microservicio **Orquestador** del proyecto `microservicios-pdf`, alineado con el
contrato compartido versión 1.0.0.

## Responsabilidad

El Orquestador coordinará posteriormente el flujo entre los microservicios de
validación, extracción y persistencia. También será responsable de propagar el
`X-Correlation-ID`, aplicar timeout y retry, ejecutar compensaciones SAGA cuando
corresponda y devolver la respuesta del microservicio de
persistencia-actualizaciones.

La implementación funcional todavía no fue realizada. No se han implementado
rutas de negocio, comunicación entre microservicios ni el flujo de coordinación.

## Arquitectura

El servicio utilizará arquitectura de N capas con las siguientes dependencias:

`controllers -> services -> repository -> infraestructura`

- `controllers/`: manejará HTTP, rutas y códigos de respuesta.
- `services/`: contendrá la coordinación entre microservicios, sin depender de
  FastAPI.
- `schemas/`: contendrá DTOs Pydantic independientes de los modelos de dominio.
- `models/`: contendrá modelos de dominio Python puro.
- `core/`: contendrá configuración, excepciones y componentes comunes.

## Estructura

```text
orquestador/
├── app/
│   ├── main.py
│   ├── controllers/
│   ├── schemas/
│   ├── services/
│   ├── models/
│   └── core/
│       ├── config.py
│       ├── exceptions.py
│       ├── repository.py
│       └── database.py
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env.example
└── README.md
```

Los directorios de pruebas quedan preparados para aplicar posteriormente el
ciclo TDD `RED -> GREEN -> REFACTOR`. No se han creado pruebas funcionales ni
pruebas vacías.

## Restricciones

El Orquestador no utilizará MongoDB, Redis ni `pypdf`. Tampoco extraerá texto,
calculará checksums, persistirá información, accederá directamente a bases de
datos ni implementará lógica propia de validación del PDF. Estas
responsabilidades pertenecen a otros microservicios.

## Instalación con uv

Instalar las dependencias declaradas y sincronizar el entorno:

```powershell
uv sync
```

## Ejecución

Desde la raíz de este microservicio:

```powershell
uv run uvicorn app.main:app --reload
```

La aplicación FastAPI queda creada como base de arranque. Las rutas de negocio,
incluidos `POST /pdf` y la futura ruta `GET /health`, todavía no están
implementadas.
