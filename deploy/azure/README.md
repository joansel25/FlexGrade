# Despliegue en Azure

**Toda la infraestructura de este proyecto es código.** Once plantillas de Bicep en `bicep/`
crean la red, la base de datos, la caché, la aplicación, los permisos, el cortafuegos de
aplicación y el autoescalado. Se levanta con un comando y se destruye con otro.

### Empieza por [`RUNBOOK.md`](RUNBOOK.md)

Es lo único que hay que abrir para recrear el sistema: cómo levantarlo, qué mirar, qué cuesta y
cómo destruirlo.

```powershell
.\estado.ps1            # ¿hay algo encendido y cuánto lleva costando?
.\levantar.ps1 demo     # levantar para sustentar
.\destruir.ps1          # apagarlo todo
```

En Git Bash, Linux o macOS, los mismos con `.sh`.

---

## Qué es el resto de este documento

Lo que sigue describe el **aprovisionamiento manual desde el portal**, que es como se hacía
antes de que existieran las plantillas. **Ya no son instrucciones**: el Bicep hace todo eso, y
hacerlo a mano ahora produciría una infraestructura distinta de la que se despliega.

Se conserva porque la columna «el detalle que arruina el paso» reúne lo que cada recurso
necesita de verdad, y eso sigue siendo útil cuando algo no arranca y hay que entender por qué.

**Tres cosas de aquí abajo están desactualizadas y conviene saberlo antes de leerlas:**

- La región `eastus` **está prohibida** por una política de la suscripción. La real es
  `centralus`.
- **Azure Cache for Redis está retirado.** El servicio vigente es Azure Managed Redis, que va
  por el puerto 10000 y no por el 6380.
- **Front Door no se despliega**, y el plan de App Service es S1, no B1. Los motivos están en
  `INFRASTRUCTURE.md`, sección 7.

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
| 8 | Application settings (hoy las pone `ajustes.bicep`) | — | `WEBSITES_PORT=8000`, o App Service busca a uvicorn en el 80 y marca el sitio como caído |
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

## 1. La configuración de la aplicación

La aplican las plantillas, en `bicep/modules/ajustes.bicep`. Los valores sensibles **no se
escriben**: son referencias `@Microsoft.KeyVault(SecretUri=...)` que App Service resuelve al
arrancar usando su identidad administrada, de modo que ningún secreto pasa por el repositorio ni
por los registros del pipeline.

Aquí vivía una plantilla llamada `app-settings.example.json`. Se eliminó porque contradecía a
las plantillas en algo con consecuencias: declaraba un pool de 10 conexiones con 20 de
desbordamiento, y con las seis instancias del pico serían 180 conexiones contra un servidor que
no las admite. El Bicep usa 5 y 10 por esa razón, y lo explica donde lo declara.

## 2. Health checks

| Ruta | Qué comprueba | Para qué sirve |
|---|---|---|
| `/health` | que el proceso responde | **Esta es la que deben usar Application Gateway y el Health check de App Service** |
| `/health/ready` | además, que PostgreSQL y Redis responden | Verificación posterior al despliegue, a mano o desde el pipeline |

Se configura con `az webapp config set --generic-configurations '{"healthCheckPath": "/health"}'`
y, en Application Gateway, en la sonda del backend pool.

Ninguna de las dos está limitada por el rate limiting, y no es un olvido: el Application Gateway
sondea `/health` cada pocos segundos. Con un límite encima, la sonda acabaría recibiendo 429, el
balanceador daría la instancia por caída y la retiraría del servicio — el limitador tumbaría la
aplicación que protege.

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

## 9. Microsoft Entra External ID — las tres vías, y dónde se corta cada una

El documento de la Fase I nombra Entra External ID; el código emite y valida sus propios JWT.
La decisión sigue abierta, y esta sección existe para que quien la tome sepa lo que cuesta cada
camino en vez de descubrirlo a mitad.

**Lo primero, porque cambia la conversación:** el puerto `AuthService` está diseñado para un
sistema que EMITE tokens —tiene `create_token`, `hash` y `verify`—. Con Entra, Entra emite los
tokens y guarda las contraseñas, y el backend solo los valida. Tres de los cuatro métodos dejan
de tener sentido. No es sustituir una pieza: es cambiar quién manda en la autenticación.

| Vía | En Azure | En el código | ¿Encaja con el frontend separado? |
|---|---|---|---|
| Dejarlo como está | — | — | Sí |
| App Service Authentication («Easy Auth») | ~1 h en el portal | ~1 día | Con fricción, ver abajo |
| Entra completo en el código | ~2 h | 3–5 días | Sí |

### 9.1 Easy Auth: lo que hace la plataforma y lo que no

Se activa en el portal (**Authentication → Add identity provider → Microsoft**). App Service
intercepta la petición ANTES de que llegue al contenedor: valida el token, rechaza a quien no
esté autenticado y pasa la identidad ya verificada en la cabecera
`X-MS-CLIENT-PRINCIPAL`. Se ahorra lo más técnico —firmas, descarga de claves públicas,
expiración—, que lo hace la plataforma.

Tres cosas que NO resuelve:

- **Autentica, no autoriza.** Entra dice «este es Juan»; que Juan sea `ADMIN` está en la tabla
  `users` de este sistema. El código sigue teniendo que leer la cabecera, buscar al usuario y
  decidir. Hace falta además una columna `external_id` en `users`: hoy la identidad es el UUID
  propio, y pasaría a ser el `oid` que emite Entra.
- **Hay que excluir `/health`.** Si Easy Auth protege todo, el Application Gateway sondea
  `/health`, recibe un redirect a la pantalla de inicio de sesión y da la instancia por caída.
  Se configura con `excludedPaths`, sin tocar código, pero olvidarlo tumba el servicio entero y
  el síntoma no señala a la autenticación por ningún lado.
- **Easy Auth funciona con COOKIES, y aquí el frontend vive en otro dominio.** Los archivos
  estáticos se sirven desde Azure Storage a través de Front Door, y la API desde App Service:
  una cookie entre dominios distintos es una cookie de terceros, y los navegadores las bloquean
  por defecto. Es exactamente la razón por la que este proyecto descartó la cookie `httpOnly`
  y guarda el access token en memoria (`frontend/src/features/auth/tokenStorage.ts`).

  Easy Auth brilla cuando la MISMA App Service sirve la web y la API. En una SPA separada,
  encaja mal.

### 9.2 La salida que no es obvia

Servir el frontend **desde el propio App Service** en vez de desde Storage haría que Easy Auth
funcionara casi sin código: mismo dominio, la cookie funciona, y de paso desaparece el problema
de CORS. El precio es alejarse del diagrama de la Fase I —que pone el frontend en Storage +
Front Door— y perder que los archivos estáticos se sirvan desde el borde.

### 9.3 Si se va a la vía completa, el radio de daño

- **Backend:** adaptador que valida contra el JWKS de Entra; `POST /auth/login` y
  `/auth/refresh` DESAPARECEN —el navegador va a Entra, no a esta API—; `users.external_id`; el
  seed deja de crear contraseñas y las cuentas de prueba se crean en el tenant.
- **Frontend:** MSAL y flujo de redirección; `tokenStorage.ts` se reescribe entero; `RequireAuth`
  y el cliente HTTP cambian de fuente de token.
- **Tests:** 13 de los 52 archivos del backend autentican, y 25 del frontend tocan tokens.
  Todos obtienen hoy el token llamando a `/auth/login`, que dejaría de existir.

**El orden importa:** si se hace, se hace DESPUÉS de tener Azure funcionando. Depurar
autenticación federada contra una infraestructura que todavía no existe es depurar dos cosas a
la vez.
