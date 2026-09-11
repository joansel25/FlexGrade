# Runbook: levantar y destruir la infraestructura

**Esto es lo único que hay que abrir para recrear el sistema en Azure.** No hace falta recordar
nada más ni guardar datos aparte: todo lo que se necesita está aquí o en el repositorio.

Si quien lo ejecuta es un asistente, basta con decirle «sigue `deploy/azure/RUNBOOK.md`».

---

## 1. Qué sobrevive y qué no

Hay dos grupos de recursos y solo uno se destruye.

### `matricula-base` — NO SE BORRA NUNCA

| Recurso | Nombre real | Qué guarda |
|---|---|---|
| Key Vault | `matricula-kv-pefjbi` | `postgres-admin-password`, `jwt-secret`, `database-url`, `redis-url` |
| Container Registry | `matriculaacrpefjbi` | La imagen `matricula-backend` |

Cuesta unos **5 USD al mes** y es el precio de que recrear el resto sea rápido y fiable.

**Por qué el Key Vault vive aquí:** tiene borrado lógico de 90 días. En el grupo efímero, su
nombre quedaría reservado al destruirlo y el siguiente despliegue fallaría con «name already in
use», sin mencionar nunca que el recurso está en la papelera.

**Por qué el ACR vive aquí:** guarda la imagen. Si se borrara, cada sesión empezaría
reconstruyéndola y subiéndola antes de poder desplegar nada.

### `matricula-demo` — SE CREA Y SE DESTRUYE

Con el perfil económico son **22 recursos**: red, PostgreSQL, Redis, App Service y el contenedor
de migraciones. Con el de demostración son **29**: los siete de más son el Application Gateway, su política de
WAF, su dirección pública, la regla de autoescalado, la cuenta de almacenamiento del frontend y
—porque el económico los apaga— el NAT Gateway con su dirección de salida.

**Los datos de la base de datos se van con él**, y por eso el despliegue vuelve a migrar y a
sembrar cada vez.

---

## 2. Datos fijos del proyecto

Están ya escritos en `bicep/parametros.*.json`. Se listan aquí para poder comprobarlos:

```
Suscripción     Azure for Students
Región          centralus
Grupo base      matricula-base
Grupo efímero   matricula-demo
Key Vault       matricula-kv-pefjbi
ACR             matriculaacrpefjbi.azurecr.io
Imagen          matricula-backend:latest
```

**La región no se elige libremente.** La suscripción tiene una política que solo permite cinco, y
`eastus` NO está entre ellas. De las permitidas, `northcentralus` no tiene zonas de
disponibilidad, así que la réplica de PostgreSQL no se puede activar allí. Se comprueban con:

```bash
az policy assignment list --disable-scope-strict-match --query "[0].parameters"
```

---

## 3. Levantar la infraestructura

Desde `deploy/azure/bicep/`. Tarda unos **25 minutos** con el perfil económico y **40** con el de
demostración, y no baja de ahí: Redis y PostgreSQL tardan lo que tardan.

**No se lanza cinco minutos antes de sustentar.**

### 3.1 Comprobar la sesión

```bash
az account show --query "{suscripcion:name, estado:state}" -o table
```

Si no hay sesión: `az login`.

### 3.2 Crear el grupo efímero

```bash
az group create --name matricula-demo --location centralus
```

### 3.3 Subir la imagen, si no está

```bash
az acr repository show-tags --name matriculaacrpefjbi --repository matricula-backend -o tsv
```

Si el repositorio existe y tiene `latest`, este paso se salta: la imagen sobrevivió.

Si falta, o si el código cambió desde la última vez:

```bash
az acr login --name matriculaacrpefjbi
docker build --tag matriculaacrpefjbi.azurecr.io/matricula-backend:latest --target runtime ./backend
docker push matriculaacrpefjbi.azurecr.io/matricula-backend:latest
```

**Hace falta Docker local.** `az acr build` —que construiría la imagen dentro de Azure— está
BLOQUEADO en esta suscripción: falla con `TasksOperationsNotAllowed`. No es un error de
configuración, es una restricción de la cuenta de estudiante.

### 3.4 Ver qué se va a crear

```bash
az deployment group what-if \
  --resource-group matricula-demo \
  --template-file main.bicep \
  --parameters @parametros.economico.json
```

Deben salir **22 recursos** con el perfil económico y **29** con el de demostración, todos
`Create`. Los `Unsupported` —la política de acceso y la
asignación de rol— **no son errores**: son recursos con nombre calculado en tiempo de despliegue
que la previsualización no sabe resolver.

**No hay que pasar ninguna contraseña.** El archivo de parámetros lleva una *referencia* al Key
Vault, no el valor:

```json
"claveAdminPostgres": {
  "reference": {
    "keyVault": { "id": ".../matricula-kv-pefjbi" },
    "secretName": "postgres-admin-password"
  }
}
```

### 3.5 Desplegar

```bash
az deployment group create \
  --resource-group matricula-demo \
  --template-file main.bicep \
  --parameters @parametros.economico.json \
  --name levantada
```

Para sustentar, con la arquitectura completa del documento —réplica de PostgreSQL y App Service
S1 con autoescalado— se cambia el archivo por `@parametros.demo.json`.

### 3.6 Comprobar que quedó bien

```bash
URL=$(az deployment group show --resource-group matricula-demo --name levantada \
      --query properties.outputs.urlSalud.value -o tsv)
curl -s "$URL"
```

Tiene que responder exactamente:

```json
{"status":"ready","dependencies":{"postgres":"ok","redis":"ok"}}
```

**Si `postgres` sale `error`**, el orden de sospechosos es: la zona DNS privada no resolvió, la
identidad administrada no pudo leer el Key Vault, o la referencia al secreto quedó sin resolver
—en ese último caso `DATABASE_URL` contiene la cadena literal `@Microsoft.KeyVault(...)`—.

La primera petición tarda unos 30 segundos: el contenedor arranca en frío.

---

## 4. Las migraciones y los datos

**Van dentro del propio despliegue.** No hay que hacer nada aparte.

PostgreSQL está inyectado en la VNet y no tiene punto de conexión público: ni una máquina local
ni un runner de GitHub lo alcanzan. Por eso `main.bicep` crea un **contenedor de un solo uso**
dentro de la red que ejecuta `alembic upgrade head && python -m app.infrastructure.seed` y muere.

Se comprueba así:

```bash
az container show --resource-group matricula-demo --name matricula-migraciones   --query "{estado:instanceView.state, salida:containers[0].instanceView.currentState.exitCode}"

az container logs --resource-group matricula-demo --name matricula-migraciones
```

Tiene que salir `Succeeded` y código **0**.

**Si el despliegue se repite sobre un grupo que ya existe**, el contenedor NO se vuelve a
ejecutar: ARM lo ve sin cambios y lo deja como está. Para forzarlo hay que borrarlo antes:

```bash
az container delete --resource-group matricula-demo --name matricula-migraciones --yes
```

Para un ambiente real, `sembrarDatos: false` en el archivo de parámetros deja solo las
migraciones, sin datos de ejemplo.

---

## 5. El autoescalado: cómo verlo y qué capturar

**Solo existe con el perfil de demostración.** El económico despliega `desplegarAutoescalado:
false` porque el nivel B1 no lo admite; ver la sección 9, hallazgo 8.

### 5.1 Comprobar que la regla existe y está activa

```bash
az monitor autoscale show --resource-group matricula-demo --name matricula-autoescalado   --query "{activa:enabled, perfiles:profiles[].name}"
```

Tienen que salir los tres perfiles: `normal`, `pico-matricula` y `fin-del-pico`.

### 5.2 Generar carga de verdad

```bash
URL=$(az deployment group show --resource-group matricula-demo --name levantada       --query properties.outputs.urlGateway.value -o tsv)

python deploy/azure/generar-carga.py --url "$URL" --hilos 40 --minutos 15
```

Golpea el **login**, no el catálogo, y la razón importa: el catálogo responde desde Redis y no
mueve la CPU ni con mil peticiones por segundo. El login verifica el hash de la contraseña, que
es caro a propósito, y es además el momento que describe la sección 5 del documento —los cinco
mil estudiantes entrando a la vez—.

**Quince minutos es el mínimo.** La regla necesita cinco por encima del 70%, la instancia nueva
tarda un par en arrancar el contenedor y luego hay otros cinco de espera. Con menos, la gráfica
se corta justo antes de lo interesante.

### 5.3 Dónde mirar, en orden

En el portal, sobre el grupo `matricula-demo`:

| Qué se ve | Dónde | Qué capturar |
|---|---|---|
| La regla y sus tres perfiles | `matricula-plan` → **Escalar horizontalmente** | Los umbrales 70/30 y las capacidades 1-2 / 6-10 |
| **Cada decisión, con su motivo** | ídem → pestaña **Historial de ejecución** | Es LA captura: dice «CPU 74% > 70% durante 5 min → 1 a 2 instancias» |
| La CPU subiendo | `matricula-plan` → **Métricas** → `CpuPercentage` | La curva cruzando el 70% |
| Cuántas instancias hay ahora | ídem → métrica `InstanceCount` | La escalera de 1 a 2 a 3 |

Las dos últimas, superpuestas en una sola gráfica, son la imagen que demuestra el requisito: la
CPU sube, cruza el umbral, y unos minutos después la línea de instancias escalona hacia arriba y
la CPU baja sola.

Desde la línea de comandos, sin portal:

```bash
# Qué decidió el autoescalado y por qué
az monitor activity-log list --resource-group matricula-demo --offset 2h   --query "[?contains(operationName.value,'autoscale')].{cuando:eventTimestamp, que:description}" -o table

# Cuántas instancias hay en este momento
az appservice plan show --resource-group matricula-demo --name matricula-plan   --query "{instancias:sku.capacity, nivel:sku.name}"
```

### 5.4 Si no hay tiempo de esperar al horario

La ventana de matrícula está programada de lunes a viernes, de 7:00 a 22:00 hora de Colombia.
Para sustentar un sábado —o para arrancar ya en seis instancias sin esperar— se despliega con:

```bash
az deployment group create --resource-group matricula-demo --template-file main.bicep   --parameters @parametros.demo.json --parameters autoescaladoEnModoDemostracion=true   --name levantada
```

Eso pone las capacidades del pico como perfil por defecto. **Cuesta 0,57 USD/hora solo de App
Service** (seis instancias S1), así que no se deja puesto.

---

## 6. El borde: WAF y el frontend

También solo en el perfil de demostración: Application Gateway WAF_v2 son ~0,46 USD/hora y no
tiene un nivel más barato.

### 6.1 Publicar el frontend

Bicep crea la cuenta de almacenamiento pero **no puede activar el sitio estático**: es una
propiedad del plano de datos, no de ARM. Son dos comandos:

```bash
CUENTA=$(az deployment group show --resource-group matricula-demo --name levantada          --query properties.outputs.cuentaFrontend.value -o tsv)

az storage blob service-properties update --account-name "$CUENTA"   --static-website --index-document index.html --404-document index.html

cd frontend && npm run build && cd ..
az storage blob upload-batch --account-name "$CUENTA" -s frontend/dist -d '$web' --overwrite
```

El documento 404 apunta también a `index.html` **a propósito**: React Router resuelve las rutas
en el navegador, y sin eso recargar la página estando en `/matricula` daría un 404 del
almacenamiento.

La URL sale de `properties.outputs.urlFrontend.value`. No se puede componer a mano: lleva un
número de zona (`z19`, `z22`…) que depende de dónde caiga la cuenta.

Después hay que autorizar ese origen en CORS, o el navegador bloquea todas las llamadas:

```bash
az webapp config appsettings set --resource-group matricula-demo --name <la-app>   --settings CORS_ALLOWED_ORIGINS="$(az deployment group show --resource-group matricula-demo     --name levantada --query properties.outputs.urlFrontend.value -o tsv | sed 's:/$::')"
```

### 6.2 Comprobar que el WAF bloquea

```bash
URL=$(az deployment group show --resource-group matricula-demo --name levantada       --query properties.outputs.urlGateway.value -o tsv)

curl -s -o /dev/null -w "normal:    %{http_code}
" "$URL/health"
curl -s -o /dev/null -w "inyeccion: %{http_code}
" "$URL/health?id=1%27%20OR%20%271%27=%271"
```

La primera tiene que dar **200** y la segunda **403**: el WAF reconoce el intento de inyección
SQL y lo corta antes de que llegue a la aplicación. Son las dos líneas que demuestran el
requisito, y valen como captura.

Los bloqueos quedan registrados:

```bash
az monitor activity-log list --resource-group matricula-demo --offset 1h   --query "[?contains(resourceId,'applicationGateways')].{cuando:eventTimestamp, que:operationName.value}" -o table
```

**Ojo con lo que esto NO cierra:** el App Service sigue siendo alcanzable por su URL
`azurewebsites.net`, así que el WAF se puede esquivar yendo directo. Se dejó así a propósito
para poder comparar las dos respuestas durante la sustentación; en un ambiente real habría que
restringir el acceso al sitio a la dirección del gateway.

---

## 7. Destruir

```bash
az group delete --name matricula-demo --yes --no-wait
```

Tarda unos diez minutos y **no hay que esperarlo**. Deja de contar el gasto casi de inmediato.

**Nunca borrar `matricula-base`.** Si se borra por error, hay que rehacer `base.bicep` y volver a
crear los secretos, y el nombre del Key Vault queda bloqueado 90 días —habría que usar otro—.

---

## 8. Coste

| Perfil | USD/hora | Sesión de 3 h | Sesión de 6 h |
|---|---|---|---|
| Económico, sin NAT (el de ahora) | **~0,071** | ~0,21 | ~0,43 |
| Económico con NAT | ~0,116 | ~0,35 | ~0,70 |
| Demostración, en reposo (1 instancia) | ~1,03 | ~3,10 | ~6,20 |
| Demostración, con la carga puesta (6-10 instancias) | ~1,50 a ~1,90 | ~4,50 a ~5,70 | ~9 a ~11 |
| Grupo base, siempre encendido | — | — | ~5 USD/mes |

Precios de `centralus` consultados contra la API de precios de Azure. De dónde sale cada línea:

| Recurso | USD/hora | Nota |
|---|---|---|
| Application Gateway WAF_v2 | **0,443** fijo + 0,0144/unidad | La partida mayor. No baja de ahí ni sin tráfico |
| PostgreSQL D2ds_v4 + réplica | ~0,40 | 2 vCore a ~0,10, y la réplica los duplica |
| App Service S1 | **0,095 por instancia** | En el pico son seis: 0,57. El B1 son 0,018 |
| NAT Gateway | 0,045 | El 37% del perfil económico él solo |
| Redis Balanced B0 | **0,036** | Son DOS nodos: la tarifa de 0,018 es por nodo |

**Las dos cifras que deciden el gasto son el WAF y el número de instancias.** Con el crédito de
100 USD caben unas quince sesiones de sustentación de tres horas, o muchísimas del perfil
económico — **siempre que el grupo efímero se destruya al terminar**.

### Lo que dijo la factura de verdad

Del 1 al 10 de septiembre se gastaron **14,02 USD**. Las tarifas cuadran tan bien que se puede
deducir el tiempo encendido: App Service, NAT, IP pública y punto de conexión privado dan los
cuatro **114 horas**. El coste real del grupo efímero fue **0,116 USD/hora** — la estimación era
correcta.

Tres cosas que solo se vieron ahí:

- **PostgreSQL costó 0,00 USD.** El `B1ms` Burstable entra en la oferta gratuita de Flexible
  Server: 750 horas al mes durante 12 meses. **El perfil de demostración la pierde**, porque
  `D2ds_v4` con réplica no está cubierto: pasar de un perfil a otro no solo añade el WAF, también
  convierte un PostgreSQL gratis en uno de ~0,40 USD/hora.
- **El NAT Gateway era el 37%** de la factura: 5,14 de 14,02 USD. Más que Redis y más que el App
  Service. Por eso ahora se puede apagar, y el perfil económico lo apaga.
- **114 horas en 10 días son 11,4 al día**, que contradice el modelo efímero entero. A ese ritmo
  son 42 USD al mes y el crédito dura 71 días. El problema nunca fue qué recursos se eligieron,
  sino cuánto se quedan encendidos.

Conviene una alerta de presupuesto, que es gratis:

```bash
az consumption budget create --budget-name credito-academico   --amount 30 --time-grain Monthly --category Cost   --start-date 2026-09-01 --end-date 2027-09-01
```

### Lo que el Advisor recomienda y NO hay que hacer

Azure Advisor propone **comprar una reserva de Redis, «ahorro potencial 172 USD/año»**. Una
reserva es un compromiso de **un año pagado por adelantado**; el crédito entero son 100 USD y
esta infraestructura vive por horas. Comprarla gastaría más de lo que hay para ahorrar en un
consumo que no va a existir.

Las otras diez recomendaciones son de alta disponibilidad —Premium, geo-replicación, mínimo dos
instancias— y todas contradicen la restricción de costes del documento. Tampoco se aplican, pero
**vale la pena llevarlas a la sustentación**: que el Advisor pida Premium y uno pueda explicar
por qué eligió no hacerlo es criterio, no descuido.


---

## 9. Cosas que solo se descubren ejecutando

Quedan anotadas porque ninguna se ve desde el código y todas costaron un intento fallido:

1. **`eastus` está prohibida** por política de la suscripción.
2. **ACR Tasks está bloqueado**: la imagen se construye en local, no en Azure.
3. **Azure Cache for Redis está retirado.** Crear uno falla con «create Azure Managed Redis
   instance instead». Ya se migró a `Microsoft.Cache/redisEnterprise`. **Y salió más CARO, no
   más barato**: la tarifa publicada de 0,018 USD/hora es POR NODO, y el nivel Balanced despliega
   dos. Son 0,036 reales frente a los 0,022 del Basic C0 — un 64% más. Lo confirman la factura
   (4,09 USD en 114 horas) y el Advisor, que menciona «2 nodos». No existe un nivel de un solo
   nodo; a cambio, la réplica y el SLA que el C0 no tenía.
4. **Un Key Vault con `accessPolicies: []` nace inservible.** Ser dueño de la suscripción no da
   acceso a los datos: hay que concederse la política explícitamente, y eso ya lo hace
   `base.bicep`.
5. **`btree_gist` no está permitida por defecto** en Azure Database for PostgreSQL. Falla con
   `extension "btree_gist" is not allow-listed for users`, y sin ella la migración `0010` no
   puede crear la restricción que impide la doble reserva de aulas. En el PostgreSQL de
   `docker-compose` esa lista no existe, así que **los 680 tests pasan sin rozar el problema**:
   solo aparece contra Azure. Las tres que usa el proyecto —`pgcrypto`, `unaccent` y
   `btree_gist`— ya van declaradas en `datos.bicep`.
6. **Container Instances necesita subred PROPIA delegada.** No puede compartir la de PostgreSQL
   ni la del App Service: una subred delegada admite un solo servicio. De ahí la quinta subred,
   `snet-tareas` (`10.0.5.0/24`).
7. **El contenedor de migraciones usa identidad ASIGNADA POR EL USUARIO**, no del sistema. Con
   una de sistema, el permiso `AcrPull` no se podría conceder antes de que el contenedor
   existiera — y la descarga de la imagen ocurre al arrancar, así que sería tarde.
8. **«SKU B1 con autoescalado» es una contradicción.** El nivel Basic NO admite autoescalado: la
   regla se crea, se ve en el portal y no dispara nunca. Hace falta Standard, que cuesta 0,095
   USD/hora por instancia frente a 0,018. Por eso `main.bicep` exige `skuAppService == 'S1'`
   para desplegar la regla — una regla muerta que aparenta funcionar es peor que no tenerla.
9. **«Pico: min 6, max 12» tampoco se puede.** El nivel Standard llega a DIEZ instancias. El
   máximo quedó en 10; un `maximum: 12` que Azure recorta en silencio engaña más que ayuda.
10. **«App Gateway -> App: 8000» no existe.** El 8000 es donde escucha uvicorn DENTRO del
    contenedor, y App Service no lo publica: termina TLS por su cuenta y solo expone el 443.
    Quien traduce al 8000 es el propio App Service con `WEBSITES_PORT`.
11. **Front Door queda descartado por precio.** El único nivel con WAF gestionado es Premium:
    **330 USD/mes de tarifa base** (Standard son 35, pero no trae WAF). Además no aparece en
    `INFRASTRUCTURE.md` — venía arrastrado de la lista de tecnologías del `CLAUDE.md`.
12. **El sitio estático no se puede activar desde Bicep.** Es una propiedad del plano de datos,
    no de ARM. Bicep crea la cuenta; activarlo y subir el `dist/` son dos comandos de la CLI,
    en la sección 6.1.
13. **El NAT Gateway es el 37% de la factura del perfil económico**, más que Redis y que el App
    Service, y el sistema no lo necesita para funcionar: App Service ya publica un conjunto
    estable de direcciones de salida (`az webapp show --query possibleOutboundIpAddresses`) y
    PostgreSQL y Redis se alcanzan por red privada. Lo pide la sección 3 del documento, así que
    se mantiene en el perfil de demostración y se apaga en el económico.
14. **PostgreSQL `B1ms` Burstable es GRATIS** los primeros 12 meses (750 h/mes). El
    `D2ds_v4` que exige la réplica NO lo es: el salto al perfil de demostración cuesta ~0,40
    USD/hora solo por ese cambio.
15. **Un perfil de autoescalado con horario dice cuándo EMPIEZA, nunca cuándo termina.** Se
    queda aplicado hasta que otro perfil lo reemplaza. Con solo «normal» + «pico», el pico
    arranca el lunes a las 7 y no se va nunca: seis instancias ardiendo un domingo de
    madrugada. De ahí el tercer perfil, `fin-del-pico`.
