# Imagen Docker del Orquestador

## Construir

Desde la raíz del repositorio:

```sh
docker build -t orquestador:local .
```

La imagen usa `uv.lock` para instalar dependencias bloqueadas. El ejecutable
`uv` sólo se utiliza durante la etapa de construcción y no queda en la imagen
final.

## Ejecutar con Consul

El repositorio incluye `docker-compose.yml`, que monta el token exclusivo del
Orquestador como secreto de solo lectura y deshabilita el fallback a URLs fijas.
El directorio `dockers/` debe estar como repositorio hermano de `Orquestador/` y
la red Docker `redutn` debe existir:

```powershell
cd ..\dockers
docker compose up -d

cd ..\Orquestador
docker compose up -d --build
```

`docker-compose.yml` usa `CONSUL_HTTP_ADDR=http://consul:8500`, el servicio real
de extracción registrado como `extraccion` y el token generado en
`../dockers/consul/generated/orchestrator.token`. El host expone el Orquestador
solo en `127.0.0.1:18000` para evitar el puerto usado por los otros servicios.
La lectura del secreto se puede comprobar sin mostrar su contenido:

```powershell
docker compose exec orquestador sh -c 'test -r /run/secrets/consul_orchestrator_token'
```

Se requiere que Consul esté levantado y que los cuatro servicios estén saludables
antes de enviar peticiones:

```powershell
Invoke-RestMethod http://127.0.0.1:18000/health
```

Si Consul no está disponible o no existen instancias `passing`, el Orquestador
responde con `DEPENDENCY_UNAVAILABLE`. No se debe habilitar
`CONSUL_FALLBACK_ENABLED` salvo que se hayan definido explícitamente las cuatro
URLs fijas y se haya aceptado ese riesgo.

## Ejecutar sin Compose

Para ejecución local, se puede publicar el puerto configurado sin montar el
secreto. Ejemplo con URLs fijas (modo no recomendado para producción):

```sh
docker run --rm --name orquestador -p 8000:8000 \
  -e VALIDACION_URL=http://validacion-pdf:8000 \
  -e EXTRACCION_URL=http://extraccion:8000 \
  -e PERSISTENCIA_ACTUALIZACIONES_URL=http://persistencia-actualizaciones:8000 \
  -e PERSISTENCIA_CONSULTAS_URL=http://persistencia-consultas:8000 \
  -e CONSUL_ENABLED=false \
  -e REQUEST_TIMEOUT_SECONDS=2.5 \
  -e RETRY_ATTEMPTS=2 \
  -e RETRY_DELAY_SECONDS=0.25 \
  orquestador:local
```

Con URLs fijas debe definirse explícitamente `CONSUL_FALLBACK_ENABLED=true` solo
si se quiere usar el fallback. Sin embargo, el camino recomendado para Docker es
Compose con el secreto ACL exclusivo.

El proceso escucha en `0.0.0.0` en el puerto `8000` por defecto. Se puede
seleccionar otro puerto pasando la variable `PORT`; el puerto publicado del
host debe coincidir con el puerto del contenedor:

```sh
docker run --rm --name orquestador -e PORT=8080 -p 8080:8080 --env-file .env orquestador:local
```

Las URLs de dependencias y la configuración de timeout/retry se proporcionan
en tiempo de ejecución, nunca durante el build. No se deben pasar secretos como argumentos de build. Para valores sensibles,
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
