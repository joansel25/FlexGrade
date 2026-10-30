# Hoja de implementación — pendientes de Bicep (secciones 10 a 15)

> **Estado (2026-10-29): I0–I8 implementadas y probadas en local; nada desplegado.**
> Decisiones aplicadas con la recomendación de la sección 2: D1 (excepción, grupos vacíos),
> D2 (`matricula-*`), D3 (sin tercer grupo), D4 (alertas 2 y 6 sobre `AppServiceHTTPLogs`),
> D5 (`etiquetaAmbiente`), D6 (purga en `true` en `base.json` — **revisar, es irreversible**),
> D8 (suscripción con `NetworkWatcherRG` fuera). **D7 sigue abierta**: los valores del equipo
> van vacíos y los scripts se niegan a desplegar sin ellos (RUNBOOK §2.1).
> Lo que se implementó, control por control y con su prueba: `MATRIZ_CONTROLES.md`.
> Desviaciones respecto a esta hoja: el diagnóstico de Redis y del Storage no se añadió (ninguna
> alerta ni consulta los lee); las consultas KQL viven en `modules/monitoreo/consultas/` para
> poder ejecutarlas en las pruebas; y apareció un defecto que la hoja no tenía, el puerto 6380 de
> Redis en los NSG (INFRASTRUCTURE §7.13).

Plan para ejecutar `BICEP_PENDIENTES_10_15.md` sobre el repositorio **tal como está**, no sobre el
que el documento supone. Cada afirmación de la fase 0 se comprobó contra el código o contra Azure
el 2026-10-29; la evidencia va al lado.

---

## 1. Hallazgos de la fase 0 que cambian el plan

| # | Hallazgo | Evidencia | Consecuencia |
|---|---|---|---|
| H1 | **Bug latente: `registrosId` está corrompido en los dos perfiles.** Vale `C:/Program Files/Git/subscriptions/...`: Git Bash convirtió la ruta al escribirlo | `parametros/demo.json:59`, `economico.json:53`; entró en `deaa779` | El próximo `levantar.sh` falla en el módulo de observabilidad. **Se corrige antes que nada** |
| H2 | **No se pueden crear grupos de Entra ID.** El inquilino es el de la universidad y la cuenta es de estudiante | Graph: `allowedToCreateSecurityGroups = false`; sin rol de directorio | Los 5 perfiles RBAC no tienen a quién asignarse (decisión D1) |
| H3 | La cuenta es **Owner de la suscripción** | `az role assignment list` | Sí se pueden desplegar RBAC, Policy, presupuesto y diagnósticos de suscripción |
| H4 | La API de presupuestos responde en *Azure for Students* | `az consumption budget list` → `0`, sin error | El presupuesto es viable; falta confirmarlo con un `what-if` |
| H5 | **Ningún recurso ni grupo tiene etiquetas** | `grep tags` sobre las plantillas: 0; `matricula-base` sin tags | Iteración entera (I1) |
| H6 | El Key Vault usa **políticas de acceso**, sin protección de purga | `base.bicep:70`, `:103` | Pasarlo a RBAC elimina además la fragilidad de la decisión 62 (redesplegar `base.bicep` borraba el permiso de la app) |
| H7 | **App Service ya cumple** 10.2: `httpsOnly`, TLS 1.2, FTPS apagado, `healthCheckPath: '/health'` | `app.bicep:56,71,73,74` | Nada que hacer |
| H8 | **Redis ya cumple** 10.2: TLS 1.2, `Encrypted`, puerto 10000 | `redis.bicep:58,69,70` | Nada que hacer |
| H9 | La sonda del gateway **ya va por 443** con el host del backend | `gateway.bicep:162-191` | Nada que hacer |
| H10 | PostgreSQL **no declara** `require_secure_transport` ni `ssl_min_protocol_version` | `postgres.bicep` solo tiene `azure.extensions` | I2 |
| H11 | La HA de PostgreSQL es `ZoneRedundant` en la MISMA subred delegada | `postgres.bicep:84-85` | Resuelve la inconsistencia 9.1 del documento: el diagrama se corrige, el Bicep no |
| H12 | Front Door y Azure DNS **no existen**; el Storage del frontend **sí**, solo con `desplegarBorde` | `modules/borde/frontend.bicep`; INFRASTRUCTURE §7.7 | Resuelve la inconsistencia 9.3 |
| H13 | **La API no tiene Application Insights**: no hay SDK ni OpenTelemetry, y la «Parte A» que cita el documento no está en el repositorio | `grep opentelemetry` vacío; no existe `SEGURIDAD_MONITOREO_FINOPS_GOBERNANZA.md` | La tabla `AppRequests` quedaría VACÍA y las alertas 2 y 6 nunca dispararían (decisión D4) |
| H14 | `ENVIRONMENT=dev` cambia los logs del backend a texto plano | `backend/app/interfaces/api/main.py:98` | La etiqueta `Ambiente` NO puede reutilizar el parámetro `ambiente` de `main.bicep` |
| H15 | Los nombres efímeros **ya son deterministas** | `main.bicep:115`: `uniqueString(resourceGroup().id)` | Cumple 1.5 sin cambios, siempre que el grupo se llame igual |
| H16 | Todos los roles y políticas integradas que pide el documento existen con ese nombre exacto | Resueltos por CLI (tabla de la sección 5) | Además apareció *Enforce SSL connection should be enabled for PostgreSQL flexible servers*, que cubre el transporte de PostgreSQL |

---

## 2. Decisiones que hay que tomar antes de implementar

Cada una lleva una recomendación. Las que tienen ⛔ bloquean una iteración.

| # | Decisión | Recomendación | Por qué |
|---|---|---|---|
| D1 ⛔ | Grupos de Entra para los 5 perfiles (H2) | Parámetros de ID **obligatorios pero vacíos**, y cada asignación con `if (!empty(...))`. Se registra como **excepción** (13.2) con motivo, alcance, responsable y vencimiento, hasta que TI de la universidad cree los grupos | Cumple «sin valores inventados» y deja el código listo. Asignar a usuarios sueltos contradice 10.1 |
| D2 | Nombres de los grupos (`rg-flexgrade-*` del documento frente a `matricula-*` reales) | **Conservar `matricula-*`** y ajustar el filtro de la consulta de 11.3 | Renombrar obliga a recrear el Key Vault (borrado lógico de 90 días) y el ACR. El documento lo permite (9.5: «o actualizar la consulta») |
| D3 | Tercer grupo de observabilidad | **No crearlo**: el workspace ya vive en `matricula-base`, que es persistente | Un grupo más es otro ciclo de vida que vigilar, sin ganancia. El documento pide persistencia, no un grupo concreto |
| D4 ⛔ | Origen de las alertas 2 y 6 (H13) | Crear Application Insights (lo pide 11.1 y queda listo para cuando se instrumente la API), pero escribir las alertas 2 y 6 sobre **`AppServiceHTTPLogs`** (columna `ScStatus`), que ya se recoge hoy | Sobre `AppRequests` las alertas estarían desplegadas y muertas. Al instrumentar la API se cambia la consulta. Hay que anotarlo en INFRASTRUCTURE §7.9, que hoy dice que no se usa Application Insights |
| D5 | Perfiles `dev`/`demo` del documento frente a `economico`/`demo` | Conservar los nombres de archivo; nuevo parámetro `etiquetaAmbiente` (`dev` en el económico, `demo` en el de demostración) | H14. Renombrar archivos rompe scripts, docs y la memoria del proyecto sin ganancia |
| D6 | Protección de purga del Key Vault | Activarla: el vault es persistente | **Es irreversible**: no se puede desactivar, y el vault no se podrá purgar en 90 días |
| D7 ⛔ | Valores reales: `dueno`, `centroCosto`, `alertEmails`, `budgetAmount`, `budgetStartDate`, `budgetEmails` | Los define el equipo | El documento prohíbe inventarlos. Sin ellos no compilan los perfiles |
| D8 | Alcance de Policy | **Suscripción**, con `notScopes: [NetworkWatcherRG]` | La suscripción está dedicada a FlexGrade. `NetworkWatcherRG` lo crea Azure sin etiquetas: en modo Deny, Azure dejaría de poder crearlo |
| D9 | Coste de las alertas de logs, que corren 24/7 en el grupo persistente | Aceptarlo y medirlo en la primera factura; las de frecuencia `PT1M` son las más caras | Hoy el grupo persistente cuesta ~5 USD/mes. Esto lo sube incluso con la demo apagada |

---

## 3. Estructura resultante

Se extiende lo existente; los módulos nuevos van por dominio, como el resto.

```
bicep/
├── suscripcion.bicep        NUEVO · targetScope subscription: etiquetas del grupo base, Activity Log,
│                              Policy, presupuesto, rol FinOps
├── base.bicep               + etiquetas, KV con RBAC, diagnósticos del KV, App Insights,
│                              retención por tabla, módulo de alertas persistentes
├── main.bicep               + etiquetas, región restringida, perfiles RBAC efímeros
├── parametros/
│   ├── economico.json · demo.json        + dueno, centroCosto, etiquetaAmbiente, vigencia, grupos
│   ├── base.json            NUEVO · hoy base.bicep se despliega a mano con un parámetro en línea
│   └── suscripcion.json     NUEVO
└── modules/
    ├── comun/               NUEVO · funciones exportadas (`@export()`), sin recursos
    │   ├── etiquetas.bicep    el objeto de 1.2, una sola vez
    │   └── nombres.bicep      nombres deterministas que comparten base.bicep y main.bicep
    ├── red/ datos/ borde/   + `tags` en cada recurso; postgres + parámetros TLS y alerta 4
    ├── aplicacion/          permisos.bicep: política de acceso → rol «Key Vault Secrets User»
    ├── operacion/           observabilidad.bicep → diagnósticos con `categoryGroup`, plan, PostgreSQL
    ├── acceso/              NUEVO · perfiles RBAC por ámbito, todos condicionados a D1
    ├── monitoreo/           NUEVO · action group y alertas 1, 2, 3, 5 y 6 (persistente)
    └── gobernanza/          NUEVO · definición personalizada, iniciativa y asignación
```

**Por qué `comun/nombres.bicep`:** las alertas viven en el grupo persistente y filtran por el
`_ResourceId` de recursos efímeros. No pueden leer salidas de un despliegue que todavía no existe,
y escribir los nombres a mano contradice el documento («los IDs se arman, nunca a mano»). Una
función exportada que usan los dos lados garantiza que el nombre que vigila la alerta es el mismo
que crea `main.bicep`.

---

## 4. Iteraciones

Una iteración es un commit. Ninguna se cierra sin `validar.sh` en verde. Las que tocan Azure,
tampoco sin un `what-if`, que contra un grupo vacío es gratis.

### I0 — Corrección y matriz de control *(sin decisiones pendientes)*

1. Corregir `registrosId` en los dos perfiles (H1).
2. **Evitar que se repita:** `validar.sh` rechaza cualquier valor de parámetro que contenga
   `Program Files` o que parezca un ID de recurso y no empiece por `/subscriptions/`.
3. Entregar `MATRIZ_CONTROLES.md`, con cuatro estados por control (descrito · en código ·
   desplegado · probado), sembrada con la sección 1.

**Cierre:** `validar.sh` falla con el valor corrompido y pasa con el correcto.

### I1 — Etiquetas y región *(necesita D5 y D7)*

1. `modules/comun/etiquetas.bicep` con la función exportada `etiquetas(ambiente, dueno, centroCosto, vigencia)`.
2. `param tags object` en **todos** los módulos, y `tags: tags` en cada recurso que las admita.
3. `@allowed(['centralus'])` en `ubicacion` de `main.bicep` y `base.bicep`.
4. `levantar.sh` crea el grupo efímero con `--tags`, leídas del perfil. Sin eso, cuando Policy pase
   a Deny, el `az group create` sin etiquetas será rechazado antes de llegar a Bicep.
   `Vigencia` = fecha del día siguiente: es una sesión.
5. `validar.sh` comprueba sobre el **ARM compilado** que todo recurso etiquetable lleva `tags`.
   Así se cumple el punto 8 del documento sin depender de la disciplina de nadie.

**Cierre:** el `what-if` muestra las cuatro etiquetas en los recursos, y `validar.sh` falla si se quita una.

### I2 — Cifrado y Key Vault *(necesita D6; con la demo DESTRUIDA)*

1. `base.bicep`: `enableRbacAuthorization: true`, sin `accessPolicies` ni el parámetro `objectIdAdministrador`, y la purga según D6.
2. `permisos.bicep`: la política de acceso pasa a «Key Vault Secrets User» sobre el vault, con
   `principalType: 'ServicePrincipal'`. AcrPull no cambia.
3. `postgres.bicep`: `require_secure_transport = ON` y `ssl_min_protocol_version = TLSv1.2`.
   **Las tres `configurations` se encadenan con `dependsOn`:** Flexible Server rechaza cambios de
   configuración simultáneos (`ServerIsBusy`), y ARM las lanzaría en paralelo.
4. Diagnóstico del Key Vault: `categoryGroup: 'audit'` + `AllMetrics`, en `base.bicep`.
5. Documentar el puerto 80 como limitación (10.2).

> ⚠️ **Al pasar a RBAC, tu cuenta pierde el acceso a los secretos**, porque las políticas de
> acceso dejan de contar. Para escribir `jwt-secret` hace falta asignarse **temporalmente**
> «Key Vault Secrets Officer» y retirarlo después (10.1 lo excluye de Bicep a propósito). El
> procedimiento va en el RUNBOOK. Las escrituras de `secretos.bicep` y `getSecret` siguen
> funcionando: son plano de control, y Owner las tiene.

**Cierre:** la app arranca y `/health/ready` responde (la identidad lee el secreto); `psql` sin
`sslmode` es rechazado.

### I3 — Perfiles RBAC *(necesita D1)*

| Perfil | Rol (GUID resuelto) | Ámbito | Dónde se declara |
|---|---|---|---|
| Infraestructura | Contributor `b24988ac…` | Los dos grupos | `base.bicep` + `main.bicep` |
| Desarrollador | Website Contributor `de139f84…` | App Service | `modules/acceso/` desde `main` |
| Desarrollador | Storage Blob Data Contributor `ba92f5b4…` | Cuenta del frontend | `modules/acceso/` desde `borde` |
| Seguridad | Resource Policy Contributor `36243c78…` | Los dos grupos | ídem |
| Seguridad | RBAC Administrator `f58310d9…` **con condición** | Los dos grupos | ídem |
| Monitoreo | Monitoring Contributor `749f88d5…` | Los dos grupos | ídem |
| Monitoreo | Log Analytics Reader `73c42c96…` | Workspace | `base.bicep` |
| FinOps | Cost Management Contributor `434105ed…` | Suscripción | `suscripcion.bicep` |
| API (identidad) | Key Vault Secrets User `4633458b…` | Solo el vault | I2 |

- Nombres `guid(scope, principalId, rol)`, `principalType: 'Group'`.
- **Storage sobre la cuenta, no sobre `$web`:** ese contenedor no existe al desplegar, porque lo
  crea `levantar.sh` al activar el sitio estático. Y es el único contenedor de la cuenta, así que
  el alcance efectivo es el mismo.
- **La condición del RBAC Administrator** limita los roles delegables a los GUID de esta tabla. La
  sintaxis (`conditionVersion: '2.0'`) se verifica contra la documentación de delegación antes de
  escribirla. Si no se puede aplicar, va como excepción (13.2).

**Cierre:** con D1 vacío, el `what-if` no crea asignaciones humanas. Con IDs reales, una operación
permitida y otra denegada por perfil.

### I4 — Observabilidad *(necesita D3 y D4)*

1. `base.bicep`: Application Insights `kind: 'web'` sobre el workspace existente.
2. `ajustes.bicep`: `APPLICATIONINSIGHTS_CONNECTION_STRING`. Se lee con un `existing` del
   componente en el grupo base: ni parámetro duplicado ni valor escrito a mano.
3. `observabilidad.bicep`:
   - App Service → `categoryGroup: 'allLogs'` + `AllMetrics`.
   - **Nuevo** plan → `AllMetrics` (lo necesita la alerta 1).
   - Gateway → `allLogs` + **`AllMetrics`**, que hoy no tiene (lo necesita la alerta 3).
   - **Nuevo** PostgreSQL → `allLogs` + `AllMetrics`.
   - Redis y Storage, solo si exponen categorías: se comprueba con `az monitor diagnostic-settings categories list`.
4. Retención por tabla en `base.bicep`, con parámetros: general 30, `AzureActivity` 90, y
   **`AppServiceConsoleLogs` 90**. Hoy la auditoría académica está ahí: son los logs JSON del
   backend. Cambiará a `AppTraces` cuando se instrumente la API.
5. `suscripcion.bicep`: exportación del Activity Log (Administrative, Security, Policy, Autoscale).

> ⚠️ El workspace tiene un **tope de 1 GB/día** (`base.bicep:147`). `allLogs` y `AllMetrics`
> suben la ingesta. Si se alcanza el tope, la recogida se corta y **las alertas 1, 2, 3 y 6
> quedan ciegas sin avisar**. Hay que vigilarlo en la primera sesión con carga.

**Cierre:** las consultas de cada tabla devuelven filas tras una sesión, y `AzureActivity` lista
operaciones de los grupos `matricula-*`.

### I5 — Alertas *(necesita D4, D7 y D9)*

`modules/monitoreo/` se despliega desde `base.bicep`, con alcance sobre el workspace:

| # | Tipo | Señal | Ventana / frecuencia / periodos |
|---|---|---|---|
| 1 | `scheduledQueryRules` | `AzureMetrics`, `CpuPercentage` del plan, promedio > 85 | `PT5M`/`PT5M`, 2 de 2 |
| 2 | `scheduledQueryRules` | `AppServiceHTTPLogs`: 5xx > 5 % con ≥ 20 peticiones (D4) | `PT5M`/`PT1M`, 1 de 1 |
| 3 | `scheduledQueryRules` | `AzureMetrics`, `UnhealthyHostCount` del gateway, mínimo > 0 | `PT1M`/`PT1M`, 3 de 3 |
| 5 | `activityLogAlerts` | Altas y bajas de `roleAssignments` y `policyAssignments` | Por evento |
| 6 | `scheduledQueryRules` | `AppServiceHTTPLogs`: más de 20 respuestas 401/403 | `PT5M`/`PT1M`, 1 de 1 |

- La **alerta 4** (`storage_percent` > 80) es un `metricAlerts` dentro de `postgres.bicep`,
  condicionada a `deployAlerts` (verdadero en `demo`).
- El action group usa `alertEmails` (D7) y `useCommonAlertSchema: true`.
- Los `_ResourceId` salen de `comun/nombres.bicep` (sección 3).
- La regla de autoescalado del 70 % no se toca.

**Cierre:** las seis reglas aparecen asociadas al action group, y se provoca una a propósito
(un 401 en bucle dispara la 6) y se recibe el correo.

### I6 — Presupuesto *(necesita D7)*

`suscripcion.bicep`: `Microsoft.Consumption/budgets` con avisos al 80 % real, al 100 % previsto y
al 100 % real, más correos y action group. **Sin acciones que borren nada.**

**Cierre:** el presupuesto aparece en Cost Management con sus tres avisos.

### I7 — Gobernanza *(necesita D8)*

1. `modules/gobernanza/`: definición personalizada de valores válidos (modo `Indexed`) e
   iniciativa con estas reglas:

   | Regla | Definición | Efecto |
   |---|---|---|
   | PostgreSQL sin acceso público | `5e1de0e3…` | Audit → Deny |
   | 4 etiquetas en recursos | `871b6d14…` × 4 | Solo Deny → `DoNotEnforce` → `Default` |
   | 4 etiquetas en grupos | `96670d01…` × 4 | ídem |
   | Valores válidos | personalizada | Audit → Deny |
   | HTTPS en App Service | `a4af4a39…` | Audit |
   | SSL en PostgreSQL Flexible | `c29c38cb…` | AuditIfNotExists |
   | Logs de Key Vault y de App Service | `cf820ca0…`, `91a78b24…` | AuditIfNotExists |

2. La asignación se hace en la suscripción con `notScopes` (D8). Un único parámetro
   `policyMode: 'audit' | 'enforce'` traduce a Audit/Deny y `DoNotEnforce`/`Default`, sin editar
   las definiciones.
3. `scripts/probar-politicas.sh`: crea `matricula-policytest`, intenta los tres despliegues
   prohibidos de 7.3, guarda cada error como evidencia y borra el grupo.

**Orden obligatorio:** se despliega en `audit`, se corrige lo que salga, se levanta la demo
entera en `audit` y solo entonces se pasa a `enforce`.

**Cierre:** pruebas positiva y negativa por regla, con evidencia.

### I8 — CI y ciclo de vida

- `validar.sh` aprende a emparejar cada perfil con su plantilla (`base.json` → `base.bicep`, …),
  añade `az bicep lint` y la comprobación de etiquetas de I1. El escaneo de secretos ya lo hace
  gitleaks sobre todo el repositorio, `.bicep` incluido.
- `scripts/desplegar-base.sh`: despliega `suscripcion.bicep` y `base.bicep`, que hoy se despliegan
  a mano siguiendo el README.

### I9 — Cierre

Matriz completa con evidencias; RUNBOOK, INFRASTRUCTURE §7 (nuevas desviaciones: D1, D2, D4 y
puerto 80), `CI_CD.md` y la memoria del proyecto (decisión 64).

---

## 5. Orden y dependencias

```
I0 ──► I1 ──► I2 ──► I4 ──► I5
        │      └───► I3
        └──────────────────► I6 ──► I7 ──► I8 ──► I9
```

I1 va primero porque las etiquetas tocan todos los archivos: hacerlo después obligaría a pasar dos
veces por cada módulo. I7 va después de I1 porque la política de etiquetas en Deny bloquearía
cualquier recurso sin ellas.

---

## 6. Fuera de alcance (sección 10 del documento)

La instrumentación de la API con Application Insights y la «Parte A», la creación de los grupos de
Entra, la asignación temporal de Secrets Officer, WCAG, el registro ante la SIC, la respuesta a
incidentes, Defender for Cloud, las pruebas de carga y restauración, los procesos de FinOps y
Slack. Ninguno es Bicep.
