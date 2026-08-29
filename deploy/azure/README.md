# Despliegue en Azure — lo que el backend espera encontrar

Esta carpeta contiene lo que hay que darle a Azure para que el backend arranque, y la lista de
comprobaciones para saber si quedó bien. **No aprovisiona nada**: la infraestructura se crea
desde el portal de Azure o con la CLI (`az`); aquí solo vive lo que el repositorio aporta.

El servicio de cómputo es **Azure App Service for Containers** (plan B1). App Service no
construye la imagen: la **descarga** de Azure Container Registry (ACR). Por eso no hay ningún
archivo de despliegue equivalente al `Dockerrun.aws.json` de Elastic Beanstalk: qué imagen
correr se le dice al recurso, no se sube en el paquete.

```bash
az webapp config container set \
  --name "$AZURE_WEBAPP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" \
  --container-image-name "${ACR_LOGIN_SERVER}/matricula-backend:${IMAGE_TAG}" \
  --container-registry-url "https://${ACR_LOGIN_SERVER}"
```

## 1. `app-settings.example.json` — la configuración del ambiente

App Service llama «application settings» a lo que el contenedor lee como variables de entorno.
El archivo de esta carpeta es la plantilla, en el formato que acepta la CLI:

```bash
sed -e "s|REEMPLAZAR_KEYVAULT|${KEYVAULT_NAME}|g" \
    -e "s|REEMPLAZAR_FRONTDOOR|${FRONTDOOR_HOSTNAME}|" \
    -e "s|REEMPLAZAR_AMBIENTE|${ENVIRONMENT}|" \
    deploy/azure/app-settings.example.json > app-settings.json

az webapp config appsettings set \
  --name "$AZURE_WEBAPP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" \
  --settings @app-settings.json
```

Los valores sensibles **no se escriben ahí**: son referencias
`@Microsoft.KeyVault(SecretUri=...)` que App Service resuelve al arrancar, usando la identidad
administrada de la aplicación. El secreto vive en Azure Key Vault y nunca pasa por el
repositorio ni por los registros del pipeline.

Para que la referencia funcione hay que habilitar la identidad administrada y darle permiso de
lectura sobre el Key Vault. Si no, App Service arranca con la cadena literal
`@Microsoft.KeyVault(...)` como valor y la aplicación falla al conectarse con un error que no
menciona el Key Vault por ningún lado — el fallo más confuso de todo el montaje:

```bash
az webapp identity assign --name "$AZURE_WEBAPP_NAME" --resource-group "$AZURE_RESOURCE_GROUP"
az keyvault set-policy --name "$KEYVAULT_NAME" --object-id "$PRINCIPAL_ID" --secret-permissions get list
```

| Variable | Obligatoria | Valor en la nube |
|---|---|---|
| `DATABASE_URL` | sí | `postgresql+psycopg://usuario:clave@<servidor>.postgres.database.azure.com:5432/matricula?sslmode=require` |
| `REDIS_URL` | sí | `rediss://:<clave>@<nombre>.redis.cache.windows.net:6380/0` — Azure Cache for Redis exige TLS |
| `JWT_SECRET` | sí | distinto por ambiente; nunca se reutiliza entre dev, staging y prod |
| `CORS_ALLOWED_ORIGINS` | sí, en cuanto exista el frontend | el dominio de Azure Front Door, p. ej. `https://matricula.azurefd.net` |
| `ENVIRONMENT` | recomendable | `dev`, `staging` o `prod`. Distinto de `dev` activa los logs en JSON |
| `DOCS_ENABLED` | recomendable | `false` en producción |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | según plan | ver el apartado 4 |
| `WEBSITES_PORT` | **sí, en contenedores** | `8000`. Sin ella App Service prueba el 80 y el 8080, no encuentra a uvicorn y marca el sitio como caído |
| `LOG_LEVEL` | opcional | `INFO` |
| `APP_VERSION` | opcional | la etiqueta del despliegue, para verla en `/health` |

Si falta alguna de las tres primeras, **la aplicación no arranca**: falla al iniciar con un
error explícito en vez de comportarse de forma rara en caliente. Es deliberado, y en un
despliegue es la diferencia entre enterarte en el minuto uno o cuando entra el primer estudiante.

`sslmode=require` en `DATABASE_URL` no es opcional: PostgreSQL Flexible Server rechaza las
conexiones en claro por defecto.

## 2. Health checks

| Ruta | Qué comprueba | Para qué sirve |
|---|---|---|
| `/health` | que el proceso responde | **Esta es la que deben usar Application Gateway y el Health check de App Service** |
| `/health/ready` | además, que PostgreSQL y Redis responden | Verificación posterior al despliegue, a mano o desde el pipeline |

Se configura con `az webapp config set --generic-configurations '{"healthCheckPath": "/health"}'`
y, en Application Gateway, en la sonda del backend pool.

**No pongas `/health/ready` ahí.** Si lo haces, una caída momentánea de PostgreSQL hará que
Application Gateway retire instancias que están sanas, el autoescalado las reemplace por otras
que fallarán igual, y un incidente de base de datos se convierta en una caída total.

Después de cada despliegue, la comprobación que de verdad dice si quedó bien configurado:

```bash
curl -s https://<tu-app>.azurewebsites.net/health/ready | jq
# {"status":"ready","dependencies":{"postgres":"ok","redis":"ok"}}
```

`redis: "degraded"` no es un fallo de despliegue: la aplicación funciona sin caché, solo más
lenta. `postgres: "error"` sí lo es, y viene con un `503`.

## 3. Ranuras de despliegue (deployment slots)

El equivalente al despliegue por lotes de Elastic Beanstalk es la **ranura de staging**: se
despliega ahí, se comprueba `/health/ready` contra la ranura, y solo entonces se intercambia con
producción. El intercambio precalienta la ranura antes de recibir tráfico, así que ninguna
petición cae en un proceso que todavía está arrancando.

```bash
az webapp deployment slot swap \
  --name "$AZURE_WEBAPP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" \
  --slot staging --target-slot production
```

Las opciones marcadas `"slotSetting": true` en la plantilla **no viajan en el intercambio**: se
quedan pegadas a su ranura. Es lo que impide que la ranura de staging acabe apuntando a la base
de datos de producción tras un swap.

## 4. Conexiones contra PostgreSQL — la cuenta que hay que hacer

Es el error de dimensionamiento más común y no da la cara hasta el pico.

Cada instancia mantiene hasta `DB_POOL_SIZE + DB_MAX_OVERFLOW` conexiones. Con los valores por
defecto son 30 por instancia. Un Flexible Server **B1ms** admite unas 50 conexiones en total,
así que:

```
4 instancias × 30 = 120 conexiones  >  50 disponibles  →  "too many connections"
```

Y ocurriría justo cuando el autoescalado sube instancias, es decir, en plena matrícula. Tres
salidas, y no son excluyentes: bajar `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` en las opciones de la
aplicación, subir de SKU, o activar **PgBouncer**, que Flexible Server trae integrado
(`pgbouncer.enabled = on`, puerto 6432). Por eso el tamaño del pool son variables de entorno y
no constantes en el código: se ajustan sin reconstruir ni redesplegar la imagen.

## 5. Red y firewall — quién habla con quién

Es lo que hace real el aislamiento de la VNet del documento del proyecto. Se implementa con
grupos de seguridad de red (NSG) por subred y con integración de VNet en App Service:

- **Application Gateway**: acepta 80/443 desde internet, en la subred pública.
- **App Service**: integración con VNet de salida y **acceso restringido a Application Gateway**
  (`az webapp config access-restriction add`), nunca abierto a `0.0.0.0/0`. El endpoint
  `*.azurewebsites.net` es público por defecto: sin esa restricción, la subred privada no
  protege nada.
- **PostgreSQL Flexible Server**: desplegado con **integración de VNet privada** (sin acceso
  público) y acepta 5432 solo desde la subred de la aplicación.
- **Azure Cache for Redis**: 6380 (TLS) solo desde la subred de la aplicación, con Private
  Endpoint.
- **NAT Gateway**: da la salida a internet de las subredes privadas con una IP fija, sin
  exponerlas a entrada.

## 6. Migraciones

Alembic corre **antes** de intercambiar la ranura, como paso del pipeline y una sola vez por
despliegue —no una vez por instancia—:

```bash
alembic upgrade head
```

Nunca se revierte una migración automáticamente, y un cambio destructivo va en dos releases
(`CI_CD.md` sección 6). El contenedor no las ejecuta al arrancar: si lo hiciera, cinco
instancias arrancando a la vez lanzarían cinco migraciones simultáneas sobre la misma base.

El runner de GitHub necesita alcanzar la base de datos para esto. Con el servidor en VNet
privada, o se usa un runner autoalojado dentro de la red, o se abre temporalmente una regla de
firewall para la IP del runner y se cierra al terminar.

## 7. Logs en Azure Monitor

El contenedor escribe JSON a stdout, una línea por evento. App Service lo recoge si están
activados los logs de contenedor, y se envía a un workspace de Log Analytics mediante una
configuración de diagnóstico:

```bash
az webapp log config --name "$AZURE_WEBAPP_NAME" --resource-group "$AZURE_RESOURCE_GROUP" \
  --docker-container-logging filesystem
```

Sin la configuración de diagnóstico hacia Log Analytics, los registros se quedan en el sistema
de archivos de la instancia y mueren con ella cuando el autoescalado la retira.

Consultas útiles en Log Analytics (KQL):

```kusto
AppServiceConsoleLogs
| extend d = parse_json(ResultDescription)
| where toint(d.status_code) >= 500
| project TimeGenerated, d.path, d.status_code, d.duration_ms
| order by TimeGenerated desc

AppServiceConsoleLogs
| extend d = parse_json(ResultDescription)
| where toreal(d.duration_ms) > 1000
| project TimeGenerated, d.path, d.duration_ms
| order by toreal(d.duration_ms) desc
```

Cada respuesta lleva la cabecera `X-Request-ID`. Cuando alguien reporte un fallo concreto, ese
valor encuentra la línea exacta:

```kusto
AppServiceConsoleLogs
| where ResultDescription contains "el-valor-reportado"
```
