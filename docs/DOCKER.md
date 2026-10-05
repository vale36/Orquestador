# Imagen Docker del Orquestador

## Construir

Desde la raíz del repositorio:

```sh
docker build -t orquestador:local .
```

La imagen usa `uv.lock` para instalar dependencias bloqueadas. El ejecutable
`uv` sólo se utiliza durante la etapa de construcción y no queda en la imagen
final.

## Ejecutar

```sh
docker run --rm --name orquestador -p 8000:8000 orquestador:local
```

El proceso escucha en `0.0.0.0` en el puerto `8000` por defecto. Se puede
seleccionar otro puerto pasando la variable `PORT`; el puerto publicado del
host debe coincidir con el puerto del contenedor:

```sh
docker run --rm --name orquestador -e PORT=8080 -p 8080:8080 orquestador:local
```

Las URLs de dependencias y la configuración de timeout/retry se proporcionan
en tiempo de ejecución, nunca durante el build:

```sh
docker run --rm --name orquestador -p 8000:8000 \
  -e VALIDACION_URL=http://validation:8000 \
  -e EXTRACCION_URL=http://extraction:8000 \
  -e PERSISTENCIA_ACTUALIZACIONES_URL=http://persistence:8000 \
  -e REQUEST_TIMEOUT_SECONDS=2.5 \
  -e RETRY_ATTEMPTS=2 \
  -e RETRY_DELAY_SECONDS=0.25 \
  orquestador:local
```

No se deben pasar secretos como argumentos de build. Para valores sensibles,
utilizar el mecanismo de secrets del entorno que ejecuta el contenedor. Los
archivos `.env` se excluyen del contexto y no se copian a la imagen.

## Healthcheck

Docker consulta `GET /health` dentro del contenedor cada 30 segundos. El
healthcheck usa el puerto configurado en `PORT`, con `8000` como valor por
defecto. El estado se puede inspeccionar con:

```sh
docker inspect --format='{{.State.Health.Status}}' orquestador
```

El proceso de la aplicación se ejecuta con el usuario sin privilegios `app`.
