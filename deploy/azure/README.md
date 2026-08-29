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

## 0. El orden de aprovisionamiento, y por qué es ese

Cada recurso necesita algo del anterior, así que saltarse el orden obliga a volver atrás. La
columna de la derecha es **el dato que hay que anotar**: es lo que después se pega en un secreto
de GitHub o en una opción de la aplicación.

| # | Recurso | Dato que hay que anotar | El detalle que arruina el paso |
|---|---|---|---|
| 1 | Grupo de recursos (`matricula`, `eastus`) | su nombre | Todo va dentro; con uno solo se borra todo junto al terminar el curso |
| 2 | Azure Container Registry | el *login server* (`xxx.azurecr.io`) | → secreto `ACR_LOGIN_SERVER` |
| 3 | PostgreSQL Flexible Server B1ms + base `matricula` | la cadena de conexión | Necesita `?sslmode=require`: el servidor rechaza las conexiones en claro |
| 4 | Azure Cache for Redis Basic C0 | la cadena de conexión | Es `rediss://` y puerto **6380**, no 6379: Azure exige TLS |
| 5 | Key Vault con `database-url`, `redis-url`, `jwt-secret` | el nombre del vault | Los tres valores salen de los pasos 3 y 4 |
| 6 | App Service Plan **B1** + Web App **for Containers** | el nombre de la app | Apuntando al ACR del paso 2 |
| 7 | Identidad administrada de la Web App + permiso `get`/`list` en el Key Vault | — | **Sin esto la app arranca con la cadena literal `@Microsoft.KeyVault(...)` como valor** y falla al conectarse, con un error que no menciona el Key Vault por ningún lado |
| 8 | Application settings desde `app-settings.example.json` | — | `WEBSITES_PORT=8000`, o App Service busca a uvicorn en el 80 y marca el sitio como caído |
| 9 | Entidad de servicio con rol Contributor sobre el grupo | su JSON | → secreto `AZURE_CREDENTIALS` |
| 10 | Storage Account con **Static website** activado | el nombre de la cuenta | → secreto `AZURE_STORAGE_ACCOUNT`. Aquí van los archivos del frontend |
| 11 | Front Door: origen al Storage (frontend) y al App Service (API) | perfil y endpoint | → secretos `FRONTDOOR_PROFILE` y `FRONTDOOR_ENDPOINT`; su dominio va a `CORS_ALLOWED_ORIGINS` y a la variable `VITE_API_BASE_URL_*` |
| 12 | VNet, NSG, NAT Gateway y Application Gateway | — | Es el aislamiento de red del documento de la Fase I |

**Con los pasos 1–9 el backend ya está desplegado y respondiendo.** Del 10 al 12 son la entrega
del frontend y el aislamiento de red: se pueden hacer después, y conviene, porque así un fallo
se atribuye a la aplicación o a la red, y no a las dos a la vez.

**Aviso de coste:** el Application Gateway (paso 12) cuesta más que todo lo demás junto y se
paga por hora mientras exista. Con crédito de Azure for Students conviene levantarlo al final y
solo cuando haga falta demostrarlo.

**Una nota sobre el diagrama de la Fase I.** La regla «Application Gateway → aplicación :8000»
no se traduce literal en App Service: el 8000 es el puerto INTERNO del contenedor
(`WEBSITES_PORT`), y el Gateway habla con el App Service por 443. El aislamiento se consigue con
restricciones de acceso, no publicando el 8000.

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

## 8. El frontend — archivos estáticos, no un servidor

El frontend compilado son archivos: `npm run build` produce `frontend/dist/`, que se sube al
contenedor `$web` del Storage Account y lo distribuye Front Door. No hay proceso, no hay
contenedor y no hay nada que reiniciar.

De ahí sale la consecuencia que más sorprende: **`VITE_API_BASE_URL` se fija al COMPILAR**. La
URL de la API queda incrustada en el JavaScript, así que no se puede cambiar después sin volver
a compilar y volver a publicar. Por eso el job del frontend en los workflows va **después** del
despliegue del backend: compilarlo antes produciría un paquete que apunta a un sitio que
todavía no existe.

```bash
# Lo que hace el pipeline, si alguna vez hay que repetirlo a mano:
cd frontend && VITE_API_BASE_URL="https://<tu-front-door>/api" npm run build

az storage blob upload-batch   --account-name "$AZURE_STORAGE_ACCOUNT"   --destination '$web' --source dist --overwrite --auth-mode login

az afd endpoint purge   --resource-group "$AZURE_RESOURCE_GROUP" --profile-name "$FRONTDOOR_PROFILE"   --endpoint-name "$FRONTDOOR_ENDPOINT" --content-paths '/*'
```

**La purga no es opcional.** Sin ella Front Door sigue sirviendo el JavaScript anterior desde
sus nodos durante horas: el despliegue habría terminado y nadie vería el cambio.

Dos cosas que hay que configurar en el Storage y que no se descubren solas:

- **El documento de índice y el de error, los dos a `index.html`.** La aplicación es una SPA con
  rutas propias (`/expediente`, `/admin/grupos`): quien entre directamente a una de ellas o
  recargue la página pide al Storage un archivo que no existe, y sin esa regla recibe un 404 en
  vez de la aplicación.
- **`CORS_ALLOWED_ORIGINS` del backend tiene que llevar el dominio de Front Door.** Frontend y
  API viven en orígenes distintos; sin esa lista el navegador bloquea todas las llamadas y la
  interfaz se ve, pero no funciona.

El **rollback del frontend no existe**: el despliegue sobrescribe los archivos y no queda
versión anterior. Recuperar una es volver a lanzar el workflow con el tag previo.
