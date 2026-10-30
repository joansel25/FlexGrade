# FlexGrade — Pendientes de Infraestructura como Código (Bicep)

Especificación de lo que falta implementar en Bicep para cumplir las secciones 10 a 15 del documento
`Proyecto_FlexGrade_Azure_Actualizado_v3`. Está escrita para el agente de programación y complementa
(no reemplaza) `INFRASTRUCTURE.md` y la Parte A de `SEGURIDAD_MONITOREO_FINOPS_GOBERNANZA.md` (código de la API).

---

## 0. Cómo usar este documento

### 0.1 Fuente de verdad y alcance

- **Fuente de verdad:** el documento del proyecto (secciones 8 a 15). Cada tarea indica la sección que la exige.
- **Alcance:** solo infraestructura como código en Bicep. Lo que no es Bicep está en la sección 10.
- **Estado de partida:** el documento declara desplegados once módulos (red, datos, aplicación, permisos,
  borde con WAF y autoescalado) y dos perfiles de parámetros, `dev` y `demo` (secciones 9.2 y 9.3).
  **Se extienden esos módulos; no se crean módulos duplicados.** Las rutas de este documento son
  sugerencias; si existe un equivalente en el repositorio, se usa el existente.

### 0.2 Reglas que no se rompen

1. **No cambiar la red ni los puertos.** Los puertos de 8.1 se mantienen: 80 (Internet → Application Gateway),
   443 (gateway → App Service), 8000 (interno del contenedor), 5432 (PostgreSQL) y 10000 con TLS (Redis).
   La ampliación no modifica puertos ni diagramas (10.2).
2. **Ningún secreto literal** en `.bicep`, `.bicepparam` ni `app-settings*.json`. Los secretos son referencias
   a Key Vault (9.2).
3. **Ningún valor inventado.** Correos, IDs de grupos de Entra, monto del presupuesto, centro de costo
   y subscriptionId entran como parámetros **sin valor por defecto** (14).
4. **Auditar antes de bloquear.** Toda regla de Azure Policy nace en modo Audit (o `DoNotEnforce`) y solo pasa
   a Deny después de validarla (13.3).
5. **Sin `Modify` ni `DeployIfNotExists`** en Policy: la remediación se hace corrigiendo el Bicep (13.3).
6. **Sin CMK ni PIM.** El cifrado en reposo usa claves administradas por la plataforma (10.2, 10.3, 13.2).
7. **Etiquetas en todo recurso que las admita**, incluidos los grupos de recursos (12.2).
8. **Orden de validación** (14): compilar y analizar → validar parámetros y permisos → `what-if` con
   credenciales autorizadas → desplegar en pruebas → comprobar comportamiento.

### 0.3 Mapa de pendientes

| Fase (sección 14) | Qué falta en Bicep | Secciones que lo exigen | Ámbito de despliegue |
|---|---|---|---|
| 0 Inventario | Nada nuevo: verificar lo existente | 9.2, 9.3, 14 | Lectura |
| 1 IAM y cifrado | 5 perfiles RBAC, identidad de la API en Key Vault, endurecimiento TLS, logs de Key Vault | 10.1, 10.2, 10.3 | Grupo de recursos |
| 2 Observabilidad | Application Insights, diagnostic settings, exportación de Activity Log, retención por tabla | 11.1, 11.2 | Grupo + suscripción |
| 3 Alertas | Action Group, 6 alertas, health check | 11.1, 11.2, 11.3 | Grupo + suscripción |
| 4 Costos | Objeto de etiquetas común, presupuesto con 3 avisos | 12.2, 12.3, 12.5 | Suscripción o grupo |
| 5 Gobernanza | Iniciativa de Azure Policy con 5 reglas, restricción de región | 13.2, 13.3 | Suscripción + grupo |
| 6 Cierre | Nada nuevo: validación final | 14, 15.3 | Pruebas |

---

## 1. Decisiones transversales (aplican a todas las fases)

### 1.1 Grupos de recursos

El documento distingue tres grupos. Sus nombres reales son un parámetro pendiente (14); se recomienda que todos
empiecen por el mismo prefijo, para que la consulta de auditoría de 11.3 los encuentre con un solo filtro.

| Grupo | Ciclo de vida | Contiene | Etiqueta `Ambiente` |
|---|---|---|---|
| Aplicación (ej. `rg-flexgrade-app-dev` / `-demo`) | Efímero: se crea y destruye por sesión (8.4.1, 9) | Red, App Service, PostgreSQL, Redis, Application Gateway, NAT, diagnostic settings y la alerta de métricas de PostgreSQL | `dev` o `demo` |
| Observabilidad (ej. `rg-flexgrade-obs`) | Persistente (7.4, 11.1) | Log Analytics workspace, Application Insights, Action Group, alertas de logs y de Activity Log | `compartido` |
| Pruebas de Policy (ej. `rg-flexgrade-policytest`) | Temporal, aislado (13.3) | Solo recursos de prueba negativa, sin datos reales | `dev` |

**Decisión a confirmar en la fase 0: ubicación del Key Vault.** El documento pide un vault dedicado a FlexGrade
(10.1), pero no dice en qué grupo vive. Se recomienda el **grupo persistente**: el borrado temporal de Key Vault
reserva el nombre durante su período de retención, así que recrear el vault con el mismo nombre en cada sesión
falla. Además, mantenerlo persistente conserva el historial de versiones del secreto JWT.

### 1.2 Objeto de etiquetas común (12.2)

Se declara una vez en el archivo principal y se pasa a **todos** los módulos. Cada recurso que admita etiquetas
recibe `tags: tags`. Las etiquetas del grupo **no se heredan** solas (12.2), así que los grupos también se crean
con etiquetas.

```bicep
@allowed([ 'dev', 'demo', 'compartido' ])
param ambiente string

@minLength(1)
param dueno string          // identificador del equipo, nunca un nombre de persona (12.2)

@minLength(1)
param centroCosto string    // código académico acordado (pendiente, 14)

param vigencia string = ''  // fecha de revisión, solo en recursos temporales (12.2)

var tags = union({
  Proyecto: 'FlexGrade'
  Dueno: dueno
  Ambiente: ambiente
  CentroCosto: centroCosto
}, empty(vigencia) ? {} : { Vigencia: vigencia })
```

- La clave técnica es `Dueno` sin ñ (12.2).
- `Vigencia` va solo en el grupo efímero y sus recursos. En el grupo persistente se omite.

### 1.3 Región (13.2)

La Circular Externa 005 de 2017 de la SIC incluye a Estados Unidos entre los países con nivel adecuado de
protección. El documento asume Central US, la región de las tarifas de 8.4.1. La región se restringe en el
parámetro, no con una regla nueva de Policy:

```bicep
@allowed([ 'centralus' ])   // añadir otra región solo si su país está en la lista de la Circular 005 (13.2)
param location string = 'centralus'
```

### 1.4 Ámbitos de despliegue

| Ámbito | Qué se despliega ahí |
|---|---|
| `targetScope = 'subscription'` | Creación de grupos con etiquetas, exportación del Activity Log, definiciones personalizadas de Policy, presupuesto (si la suscripción es dedicada) |
| `targetScope = 'resourceGroup'` | Todo lo demás: RBAC sobre recursos, Application Insights, diagnostic settings, alertas, asignaciones de Policy por grupo |

La cuenta que despliega las asignaciones RBAC y de Policy debe tener esa facultad (Owner o User Access
Administrator / RBAC Administrator). La habilitación inicial la hace una cuenta que ya la tenga (10.1).

### 1.5 Perfiles `dev` y `demo`

| Recurso nuevo | `dev` | `demo` |
|---|---|---|
| Application Insights y diagnostic settings | Sí | Sí |
| Alerta de métricas de PostgreSQL (fase 3, alerta 4) | Opcional (`deployAlerts = false`) | Sí (`deployAlerts = true`) |
| RBAC, Key Vault, presupuesto, Policy, Action Group, alertas de logs y de Activity Log | Persistentes: no dependen del perfil | Persistentes |

Las alertas de logs viven en el grupo persistente y filtran por `_ResourceId`. Para que sigan funcionando de una
sesión a otra, **los recursos efímeros deben conservar el mismo nombre en cada despliegue** (nombres deterministas,
sin sufijos aleatorios). Si no hay infraestructura desplegada, no llegan datos y las alertas no se disparan.

El perfil `dev` sigue sin WAF ni réplica (8.4.1); esta ampliación no cambia esa regla.

---

## 2. Fase 0 — Inventario (prerequisito, sin código nuevo)

**Objetivo (14):** comparar el estado real con la sección 10 antes de escribir nada.

Revisar en los once módulos y en Azure:

- [ ] Qué módulo crea cada recurso de 8.2 (App Service S1, PostgreSQL D2ds_v4 con HA, Managed Redis Balanced B0,
      Application Gateway WAF_v2, NAT, VNet y subredes).
- [ ] Si **Front Door, Azure DNS y Storage Static Website** (listados en los componentes de 8) están desplegados
      por Bicep. El documento los describe, pero 9.3 no confirma su despliegue. Lo que exista recibe etiquetas,
      diagnósticos y Policy como el resto; lo que no exista se documenta.
- [ ] En qué grupo vive hoy el Key Vault (ver 1.1).
- [ ] Qué hace hoy el módulo de permisos (¿solo la identidad de la API en Key Vault?).
- [ ] Ruta y protocolo de la sonda del Application Gateway (debe ir por 443 con el nombre de host del backend, 9.3).
- [ ] Si `httpsOnly`, `minTlsVersion` y los parámetros TLS de PostgreSQL ya están declarados.
- [ ] Cómo está declarada la alta disponibilidad de PostgreSQL (ver la sección 9, punto 1).

**Entregable (criterio de cierre de 14):** una matriz de control con cuatro estados por control:
descrito, presente en código, desplegado y probado. Cada estado debe tener su evidencia.

---

## 3. Fase 1 — IAM y cifrado (secciones 10.1, 10.2, 10.3)

**Módulo sugerido:** extender el módulo de permisos existente.

### 3.1 Cinco perfiles con privilegio mínimo (10.1)

Las asignaciones van a **grupos de Entra ID** (no a usuarios sueltos). Los grupos se crean fuera de Bicep;
sus object IDs entran como parámetros.

| Perfil | Parámetro | Rol integrado (nombre exacto) | Ámbito |
|---|---|---|---|
| Administrador de infraestructura | `infraAdminsGroupId` | Contributor | Grupos de recursos de FlexGrade |
| Desarrollador | `developersGroupId` | Website Contributor | App Service de la API |
| Desarrollador | `developersGroupId` | Storage Blob Data Contributor | Contenedor `$web` del Storage del frontend |
| Seguridad y gobernanza | `securityGroupId` | Resource Policy Contributor | Grupos del proyecto |
| Seguridad y gobernanza | `securityGroupId` | Role Based Access Control Administrator (con condición) | Grupos del proyecto |
| Operador de monitoreo | `monitoringGroupId` | Monitoring Contributor | Recursos vigilados + grupo de observabilidad |
| Operador de monitoreo | `monitoringGroupId` | Log Analytics Reader | Workspace |
| Responsable FinOps | `finopsGroupId` | Cost Management Contributor | Ámbito del presupuesto (12.3) |
| Identidad administrada de la API (no es un perfil humano) | — | Key Vault Secrets User | Solo el Key Vault de FlexGrade |

Reglas de implementación:

- **Resolver los GUID de los roles por CLI**, nunca de memoria:
  `az role definition list --name "Website Contributor" --query "[0].name" -o tsv`.
- Nombre idempotente de cada asignación: `guid(scope, principalId, roleDefinitionId)`.
- `principalType: 'Group'` para los perfiles y `principalType: 'ServicePrincipal'` para la identidad administrada.
- **Condición del RBAC Administrator:** se declara con `condition` y `conditionVersion: '2.0'`. Debe limitar los
  roles delegables a la lista aprobada de esta tabla. Antes de escribir la expresión, verificar la sintaxis en la
  documentación de delegación condicionada (fuente [21] del documento). Si la condición no se puede aplicar,
  se registra como excepción con motivo, alcance, responsable y vencimiento (13.2).
- **Key Vault Secrets Officer no va en Bicep:** se asigna de forma temporal y registrada solo para dar de alta
  o rotar secretos (10.1).
- **Storage Blob Data Contributor sobre `$web`:** solo si el Storage del frontend existe (fase 0).

```bicep
resource ra 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(apiApp.id, developersGroupId, websiteContributorRoleId)
  scope: apiApp
  properties: {
    principalId: developersGroupId
    principalType: 'Group'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', websiteContributorRoleId)
  }
}
```

### 3.2 Key Vault (10.1, 10.3)

- `enableRbacAuthorization: true` (sin políticas de acceso heredadas).
- Borrado temporal activo (comportamiento por defecto). La protección de purga se decide junto con la ubicación
  del vault (1.1): si está en el grupo persistente, se puede activar sin bloquear las sesiones efímeras.
- **Diagnostic setting** del vault al workspace con `categoryGroup: 'audit'`. Esto cumple "habilitar registros de
  acceso a Key Vault" (10.3).
- Secretos que guarda: el secreto JWT (7.4) y, si existen, las credenciales de PostgreSQL y Redis (10.3).
  Para la rotación sin corte del JWT se agrega el secreto opcional `jwt-secret-previous` (ver Parte A, A6).

### 3.3 Cifrado en tránsito por tramo (10.2)

| Tramo | Recurso | Configuración a declarar |
|---|---|---|
| Gateway → App Service (443) | `Microsoft.Web/sites` | `httpsOnly: true`, `siteConfig.minTlsVersion: '1.2'` |
| App Service: superficie extra | `Microsoft.Web/sites` | `siteConfig.ftpsState: 'Disabled'` (endurecimiento SE:08 de 15.1) |
| API → PostgreSQL (5432) | `Microsoft.DBforPostgreSQL/flexibleServers/configurations` | `require_secure_transport = 'ON'` y `ssl_min_protocol_version = 'TLSv1.2'` |
| API → Redis (10000) | `Microsoft.Cache/redisEnterprise` + `/databases` | `minimumTlsVersion: '1.2'` en el clúster; `clientProtocol: 'Encrypted'` y `port: 10000` en la base de datos |
| Ingreso por 80 | Application Gateway | **No se cambia.** Queda documentado como limitación (10.2) |

- Los parámetros de PostgreSQL se declaran como recursos hijos `configurations`, con `source: 'user-override'`.
- El cifrado en reposo ya lo da la plataforma: **no declarar CMK** (10.2).

### 3.4 Criterio de cierre (14)

- [ ] Cinco perfiles asignados a grupos, más la identidad de la API con un solo rol.
- [ ] Por cada perfil, una operación permitida y otra denegada, con evidencia.
- [ ] Prueba de lectura del secreto por la identidad administrada.
- [ ] Prueba de TLS por tramo: conexión cifrada válida; conexión sin cifrar o con certificado no confiable, rechazada.

---

## 4. Fase 2 — Observabilidad (secciones 11.1, 11.2)

**Módulo sugerido:** `observability` en el grupo persistente, más un submódulo de diagnósticos en el grupo efímero.

### 4.1 Application Insights basado en workspace

- `Microsoft.Insights/components`, `kind: 'web'`, `Application_Type: 'web'`, `WorkspaceResourceId` apuntando al
  **workspace persistente existente** (no se crea otro workspace, 11.1).
- Salida `connectionString`, cargada en la app setting `APPLICATIONINSIGHTS_CONNECTION_STRING` del App Service.
- Se crea en el grupo persistente para que la telemetría sobreviva a las sesiones.

### 4.2 Diagnostic settings hacia el workspace

| Recurso | Configuración |
|---|---|
| App Service (API) | `logs: [{ categoryGroup: 'allLogs', enabled: true }]`, `metrics: [{ category: 'AllMetrics', enabled: true }]` |
| App Service Plan | `AllMetrics` (lo necesita la alerta 1 de la fase 3) |
| Application Gateway (incluye logs del WAF) | `allLogs` + `AllMetrics` (las métricas las necesita la alerta 3 de la fase 3) |
| PostgreSQL Flexible Server | `allLogs` + `AllMetrics` |
| Key Vault | `audit` (fase 1) + `AllMetrics` |
| Redis, Front Door, Storage | Solo si existen y exponen categorías (fase 0) |

- Usar `categoryGroup` (`allLogs` o `audit`) en lugar de escribir nombres de categoría a mano.
- Cada diagnostic setting nace con el recurso, en el mismo módulo, para que se recree en cada sesión.
- La ingestión de logs cuesta: el volumen se revisa en la fase Optimizar de FinOps (12.1, 12.5).

### 4.3 Exportación del Activity Log (11.1, 11.3)

El Activity Log se envía al workspace con una diagnostic setting **a nivel de suscripción**
(`targetScope = 'subscription'`). Sin ella, la consulta de auditoría de 11.3 no devuelve resultados.

```bicep
targetScope = 'subscription'

resource activityLogToWorkspace 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'flexgrade-activitylog'
  properties: {
    workspaceId: workspaceId
    logs: [
      { category: 'Administrative', enabled: true }
      { category: 'Security', enabled: true }
      { category: 'Policy', enabled: true }
      { category: 'Autoscale', enabled: true }
    ]
  }
}
```

### 4.4 Retención por tabla (11.2)

| Tabla | Días | Motivo |
|---|---|---|
| Retención general del workspace | 30 | Logs generales (11.2) |
| `AzureActivity` | 90 | Auditoría crítica de administración |
| Tabla de la auditoría académica (`AppEvents` o `AppTraces`, según la Parte A, A3) | 90 | Auditoría crítica de matrículas |

- Se declara con `Microsoft.OperationalInsights/workspaces/tables` (`retentionInDays`).
- Los días son parámetros (`retentionGeneralDays = 30`, `retentionAuditDays = 90`), porque el documento los marca
  como pendientes de validar en soporte y costo (11.2, 14).

### 4.5 Criterio de cierre (14)

- [ ] Una solicitud a la API y un evento de matrícula aparecen en el workspace.
- [ ] Llegan logs de App Service, del WAF, de PostgreSQL y de Key Vault.
- [ ] La consulta `AzureActivity` de 11.3 devuelve operaciones de los grupos de FlexGrade.

---

## 5. Fase 3 — Alertas (secciones 11.1, 11.2, 11.3)

**Módulo sugerido:** `alerts`. El Action Group, las alertas de logs (1, 2, 3 y 6) y la de Activity Log (5) van en el
grupo persistente. La alerta de métricas de PostgreSQL (4) va junto al servidor, en el grupo efímero, controlada
por `deployAlerts`.

### 5.1 Action Group (11.2)

- `Microsoft.Insights/actionGroups`, `location: 'global'`, `groupShortName` de 12 caracteres como máximo.
- `emailReceivers` desde el parámetro `alertEmails` (array, **sin valor por defecto**) y `useCommonAlertSchema: true`.
- Slack es opcional mediante Logic App y **no** se implementa en esta fase (11.2).

### 5.2 Las seis alertas (tabla de 11.1)

| # | Alerta | Recurso Bicep | Señal exacta | Ventana / frecuencia / periodos | Grupo |
|---|---|---|---|---|---|
| 1 | Saturación sostenida | `scheduledQueryRules` sobre `AzureMetrics` | `CpuPercentage` del App Service Plan, promedio > 85 | `PT5M` / `PT5M` / 2 de 2 periodos = 10 min | Persistente |
| 2 | Errores de la API | `scheduledQueryRules` | Consulta 5xx de 11.3 (abajo); alerta si devuelve ≥ 1 fila | `PT5M` / `PT1M` / 1 de 1 | Persistente |
| 3 | Disponibilidad | `scheduledQueryRules` sobre `AzureMetrics` | `UnhealthyHostCount` del Application Gateway, mínimo > 0 | `PT1M` / `PT1M` / 3 de 3 periodos | Persistente |
| 4 | Capacidad de PostgreSQL | `metricAlerts` | `storage_percent`, `Average` > 80 | `PT15M` / `PT5M` | Efímero |
| 5 | Cambios de permisos o políticas | `activityLogAlerts` | Alta o baja de `roleAssignments` y `policyAssignments` | Por evento | Persistente |
| 6 | Accesos inusuales | `scheduledQueryRules` | Más de 20 respuestas 401/403 en `AppRequests` | `PT5M` / `PT1M` / 1 de 1 | Persistente |

- **La regla de autoescalado del 70 % no se toca.** La alerta 1 es independiente (11.1).
- Las métricas `CpuPercentage` (serverfarms), `UnhealthyHostCount` (applicationGateways) y `storage_percent`
  (PostgreSQL Flexible) existen con granularidad de 1 minuto en Azure Monitor.
- **Por qué las alertas 1 y 3 son alertas de logs y no de métricas:** una alerta de métricas con umbral estático
  solo admite ventanas de 1, 5, 15 o 30 minutos y de 1, 6 o 12 horas o 1 día. No acepta 3 ni 10 minutos y no cuenta
  periodos consecutivos. La alerta de logs sí lo hace, con `failingPeriods`
  (`numberOfEvaluationPeriods` y `minFailingPeriodsToAlert`). Así se respeta lo que pide 11.1: 10 minutos
  sostenidos y tres fallos seguidos de 1 minuto.
- Las alertas 1 y 3 leen la tabla `AzureMetrics`, así que requieren el diagnostic setting con `AllMetrics` del
  App Service Plan y del Application Gateway (4.2). Los datos llegan al workspace con unos minutos de retraso; la
  alerta puede dispararse un poco después del evento real.

**Alerta 1: consulta.** Usar `metricMeasureColumn: 'Average'`, `timeAggregation: 'Average'`,
`operator: 'GreaterThan'`, `threshold: 85` y
`failingPeriods: { numberOfEvaluationPeriods: 2, minFailingPeriodsToAlert: 2 }`.

```kusto
AzureMetrics
| where _ResourceId =~ '<ID_APP_SERVICE_PLAN>'
| where MetricName == 'CpuPercentage'
```

**Alerta 3: consulta.** Usar `metricMeasureColumn: 'Minimum'`, `timeAggregation: 'Minimum'`,
`operator: 'GreaterThan'`, `threshold: 0` y
`failingPeriods: { numberOfEvaluationPeriods: 3, minFailingPeriodsToAlert: 3 }`.

```kusto
AzureMetrics
| where _ResourceId =~ '<ID_APPLICATION_GATEWAY>'
| where MetricName == 'UnhealthyHostCount'
```

Los IDs se arman con las salidas de los módulos, nunca escritos a mano.

**Alerta 2: consulta de 11.3 (se usa tal cual).**

```kusto
AppRequests
| where TimeGenerated >= ago(5m)
| where _ResourceId =~ '<ID_APPLICATION_INSIGHTS>'
| summarize Total = sum(ItemCount),
    Fallos = sumif(ItemCount, toint(ResultCode) >= 500 and toint(ResultCode) <= 599)
| where Total >= 20
| extend Porcentaje5xx = 100.0 * Fallos / Total
| where Porcentaje5xx > 5
```

En `scheduledQueryRules`: `timeAggregation: 'Count'`, `operator: 'GreaterThan'`, `threshold: 0`,
`evaluationFrequency: 'PT1M'`, `windowSize: 'PT5M'`. El `<ID_APPLICATION_INSIGHTS>` se arma con la salida de 4.1,
nunca escrito a mano.

**Alerta 6: consulta derivada de 11.1 (mismo patrón).**

```kusto
AppRequests
| where _ResourceId =~ '<ID_APPLICATION_INSIGHTS>'
| where ResultCode in ('401', '403')
| summarize Denegadas = sum(ItemCount)
| where Denegadas > 20
```

**Alerta 3: cómo se implementa la disponibilidad.** El documento pide "tres pruebas consecutivas fallidas del
endpoint de salud, a intervalos de 1 minuto, desde un punto con acceso" (11.1). La implementación que lo cumple
usa la sonda interna del Application Gateway:

- La sonda llama a `/health` por 443 (fase 0).
- La alerta de logs sobre `UnhealthyHostCount`, con periodos de 1 minuto y 3 de 3 periodos fallidos, equivale a
  tres fallos seguidos.
- Además se declara `siteConfig.healthCheckPath: '/health'` en el App Service, para que la plataforma retire del
  reparto a las instancias que no responden.
- **Complemento opcional:** una prueba estándar de Application Insights (`Microsoft.Insights/webtests`,
  `kind: 'standard'`) contra la URL pública de entrada a `/health/ready`. Esa prueba se ejecuta por defecto cada
  5 minutos desde cada ubicación y exige que el endpoint sea alcanzable desde Internet; la recomendación oficial es
  usar al menos 5 ubicaciones con umbral de alerta de 3. Ver la sección 9, punto 2.

**Alerta 5: Activity Log.**

```bicep
resource rbacPolicyChanges 'Microsoft.Insights/activityLogAlerts@2020-10-01' = {
  name: 'flexgrade-cambios-permisos-politicas'
  location: 'global'
  tags: tags
  properties: {
    enabled: true
    scopes: [ subscription().id ]
    condition: {
      allOf: [
        { field: 'category', equals: 'Administrative' }
        {
          anyOf: [
            { field: 'operationName', equals: 'Microsoft.Authorization/roleAssignments/write' }
            { field: 'operationName', equals: 'Microsoft.Authorization/roleAssignments/delete' }
            { field: 'operationName', equals: 'Microsoft.Authorization/policyAssignments/write' }
            { field: 'operationName', equals: 'Microsoft.Authorization/policyAssignments/delete' }
          ]
        }
      ]
    }
    actions: { actionGroups: [ { actionGroupId: actionGroup.id } ] }
  }
}
```

Si la suscripción no es dedicada, `scopes` se limita a los IDs de los grupos de FlexGrade.

### 5.3 Criterio de cierre (14)

- [ ] Una alerta provocada en el entorno de pruebas, con el correo recibido y la actuación registrada.
- [ ] Las seis reglas visibles en Azure Monitor y asociadas al Action Group.
- [ ] La prueba de salud no ejecuta matrículas (11.1).

---

## 6. Fase 4 — Costos (secciones 12.2, 12.3, 12.5)

### 6.1 Etiquetas en todos los recursos

- Aplicar el objeto de 1.2 en cada módulo y a los grupos de recursos.
- Para lo que no admite etiquetas, la asignación del costo se hace por ID de recurso o de grupo (12.2);
  no requiere código.

### 6.2 Presupuesto mensual B (12.3)

- **Ámbito:** la suscripción, si está dedicada a FlexGrade. Si es compartida, uno o varios presupuestos que
  cubran **todos** los grupos de FlexGrade, incluido el persistente (12.3).
- **Antes de desplegar:** confirmar la moneda y que la oferta académica admita presupuestos de Cost Management (12.3).
- `amount` es el parámetro `budgetAmount`, **sin valor por defecto** (12.3, 14).
- `timePeriod.startDate` es el primer día de un mes (parámetro `budgetStartDate`).
- Un presupuesto **avisa, no detiene** el consumo. No se asocia ninguna acción que borre recursos o datos (12.3).

```bicep
targetScope = 'subscription'

param budgetAmount int
param budgetStartDate string        // 'AAAA-MM-01'
param budgetEmails array
param actionGroupId string

resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: 'flexgrade-presupuesto-mensual'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      consumoReal80: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        thresholdType: 'Actual'
        contactEmails: budgetEmails
        contactGroups: [ actionGroupId ]
      }
      prevision100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: budgetEmails
        contactGroups: [ actionGroupId ]
      }
      consumoReal100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: budgetEmails
        contactGroups: [ actionGroupId ]
      }
    }
  }
}
```

### 6.3 Relación con el ciclo FinOps (12.5)

| Fase FinOps | Qué aporta este Bicep |
|---|---|
| Informar | Etiquetas (asignación) y presupuesto con previsión |
| Optimizar | Perfiles `dev`/`demo` e infraestructura efímera (ya existentes); retención de logs parametrizada (4.4) |
| Operar | Avisos del presupuesto, rol Cost Management Contributor (3.1) y política de etiquetas obligatorias (7.1) |

El chargeback y el cierre mensual son procesos, no Bicep (sección 10).

### 6.4 Criterio de cierre (14)

- [ ] Todos los recursos etiquetables tienen las cuatro etiquetas obligatorias.
- [ ] El presupuesto es visible con sus tres avisos.
- [ ] El total del reporte por `CentroCosto` concilia con Azure.

---

## 7. Fase 5 — Gobernanza (secciones 13.2, 13.3)

**Módulo sugerido:** `policy`. Las definiciones personalizadas se crean a nivel de suscripción; las asignaciones,
sobre los grupos del proyecto (13.3).

### 7.1 Iniciativa FlexGrade: las cinco reglas de 13.3

| Regla (13.3) | Definición | Efecto inicial → final |
|---|---|---|
| Base de datos sin acceso público | Integrada: *Public network access should be disabled for PostgreSQL flexible servers* | Audit → Deny |
| Etiquetas obligatorias | Integrada *Require a tag on resources* × 4 (`Proyecto`, `Dueno`, `Ambiente`, `CentroCosto`), más *Require a tag on resource groups* × 4 | `enforcementMode: 'DoNotEnforce'` → `'Default'` |
| Valores de ambiente válidos | Personalizada (abajo), modo `Indexed` | Audit → Deny |
| Transporte seguro | Integrada: *App Service apps should only be accessible over HTTPS*. Para PostgreSQL, usar una integrada solo si aplica a Flexible Server; si no existe, la cobertura es la prueba real de conexión que el documento ya exige | Audit |
| Registros de diagnóstico | Integradas de auditoría de logs de recursos (por ejemplo, *Resource logs in Key Vault should be enabled* y *App Service apps should have resource logs enabled*) | AuditIfNotExists |

- **Resolver los IDs de las integradas por CLI**, nunca de memoria:
  `az policy definition list --query "[?displayName=='Require a tag on resources'].name" -o tsv`.
  Si un nombre no aparece tal cual, buscar la definición equivalente y documentarla.
- *Require a tag on resources* solo tiene efecto Deny; por eso se observa primero con `DoNotEnforce` (13.3).
- No ampliar el alcance más allá de esta tabla: el frontend y la entrada son públicos por diseño.

**Regla personalizada de valores válidos:**

```json
{
  "mode": "Indexed",
  "parameters": {
    "effect": { "type": "String", "allowedValues": ["Audit", "Deny"], "defaultValue": "Audit" }
  },
  "policyRule": {
    "if": {
      "anyOf": [
        { "field": "tags['Ambiente']", "notIn": ["dev", "demo", "compartido"] },
        { "field": "tags['Dueno']", "equals": "" },
        { "field": "tags['CentroCosto']", "equals": "" }
      ]
    },
    "then": { "effect": "[parameters('effect')]" }
  }
}
```

### 7.2 Despliegue controlado (13.3)

1. Asignar todo en Audit o `DoNotEnforce`.
2. Inventariar incumplimientos y corregirlos en el Bicep (no con `Modify` ni `DeployIfNotExists`).
3. Pasar a Deny o `Default` con un parámetro (`policyMode = 'audit' | 'enforce'`), sin editar las definiciones.
4. Recordar que Deny frena lo nuevo, pero no repara lo existente.

### 7.3 Pruebas negativas (13.3)

En el grupo aislado de pruebas, sin datos reales:

- [ ] Crear un recurso sin la etiqueta `Dueno` → rechazado.
- [ ] Crear un recurso con `Ambiente = 'produccion'` → rechazado.
- [ ] Crear o actualizar PostgreSQL con acceso público → rechazado.
- [ ] Conservar cada error de Policy como evidencia.

### 7.4 Criterio de cierre (14)

- [ ] Prueba positiva (despliegue conforme) y prueba negativa (bloqueo) de cada regla.
- [ ] Excepciones justificadas con motivo, alcance, responsable y vencimiento.
- [ ] PostgreSQL privado y conforme.

---

## 8. Validación en CI (sección 14)

Agregar al workflow existente (sin credenciales de la suscripción, 9.2):

- [ ] `az bicep build` sobre todos los archivos `.bicep`.
- [ ] `bicep lint` sin errores.
- [ ] Verificación de que cada módulo declara y aplica `tags`.
- [ ] Escaneo de secretos sobre `.bicep`, `.bicepparam` y `app-settings*.json`.
- [ ] `what-if` y despliegue solo con credenciales autorizadas, fuera del CI público.

---

## 9. Inconsistencias que el agente debe resolver con el equipo antes de implementar

1. **Réplica en espera de PostgreSQL en otra subred.** El diagrama de 8 la muestra en una subred de respaldo
   separada. En la plantilla de Flexible Server, la alta disponibilidad se declara en el mismo servidor
   (`highAvailability.mode` y `standbyAvailabilityZone`) con una sola subred delegada
   (`network.delegatedSubnetResourceId`); no hay propiedad para ubicar el standby en otra subred. Lo que sí puede
   ir en otra subred es una **réplica de lectura** (otro servidor). **Acción:** confirmar en la fase 0 qué se
   desplegó y alinear el diagrama con eso, sin cambiar el Bicep para forzar una topología que la plataforma no admite.
2. **Ventanas de las alertas 1 y 3.** Las pruebas estándar de Application Insights corren por defecto cada 5 minutos
   por ubicación y requieren un endpoint público. Además, las alertas de métricas no aceptan ventanas de 3 ni de 10
   minutos. Por eso la alerta 3 usa la sonda interna del Application Gateway, y las alertas 1 y 3 se implementan como
   alertas de logs con periodos consecutivos (5.2). **Acción:** si se quiere, aclarar en 11.1 el mecanismo usado;
   los umbrales del documento no cambian.
3. **Front Door, Azure DNS y Storage Static Website.** Aparecen en los componentes de 8, pero su despliegue no está
   confirmado en 9.3. **Acción:** resolver en la fase 0 y documentar.
4. **Ubicación del Key Vault.** Ver 1.1. **Acción:** confirmar si va en el grupo persistente.
5. **Nombres reales de los grupos.** El filtro `rg-flexgrade` de 11.3 es una convención propuesta. **Acción:** usar
   el mismo prefijo en todos los grupos o actualizar la consulta.

---

## 10. Lo que NO se implementa en Bicep

| Pendiente | Dónde se resuelve | Sección |
|---|---|---|
| Crear los grupos de Entra ID, exigir MFA y dar de alta usuarios | Administrador del directorio | 10.1 |
| Asignación temporal de Key Vault Secrets Officer para rotar secretos | Procedimiento registrado | 10.1 |
| Instrumentar FastAPI, la auditoría académica, `/health`, TLS del cliente y la rotación de JWT | Código de la API (Parte A) | 10.2, 10.3, 11 |
| Validar el frontend contra WCAG 2.1 AA | Código del frontend | 13.2 |
| Inscribir la base de datos en el Registro Nacional de Bases de Datos | La institución | 13.2 |
| Clasificar los datos académicos | Proceso del equipo | 15.3 (SE:03) |
| Procedimiento de respuesta a incidentes con reporte a la SIC y al CSIRT de Gobierno | Documento operativo | 15.3 (SE:12) |
| Medir la postura con el Microsoft cloud security benchmark en Defender for Cloud | Revisión en el portal | 13.2, 15.3 |
| Pruebas de restauración y de carga | Fase 6 de 14 | 13.1, 15.3 |
| Reporte simulado de chargeback, revisiones FinOps y cierre mensual | Proceso FinOps | 12.4, 12.5 |
| Integración con Slack | Futuro, mediante Logic App | 11.2 |
| Modelado de amenazas y pruebas de seguridad | Proceso del equipo | 15.1 (SE:11) |

---

## 11. Parámetros pendientes

Ninguno lleva valor por defecto inventado. Se declaran en los `.bicepparam` de `dev` y `demo` o en un archivo de
parámetros del grupo persistente.

| Parámetro | Tipo | Uso | Quién lo define |
|---|---|---|---|
| `subscriptionId`, nombres de grupos | string | Ámbitos | Equipo |
| `location` | string (`@allowed`) | Región verificada (13.2) | Equipo |
| `infraAdminsGroupId`, `developersGroupId`, `securityGroupId`, `monitoringGroupId`, `finopsGroupId` | string | RBAC (3.1) | Administrador de Entra |
| `alertEmails` | array | Action Group (5.1) | Equipo |
| `budgetAmount` | int | Presupuesto (6.2) | FinOps, con el saldo disponible |
| `budgetStartDate` | string | Presupuesto (6.2) | FinOps |
| `budgetEmails` | array | Presupuesto (6.2) | FinOps |
| `dueno`, `centroCosto`, `ambiente`, `vigencia` | string | Etiquetas (1.2) | Equipo |
| `retentionGeneralDays`, `retentionAuditDays` | int | Retención (4.4) | Operador, validando costo |
| `deployAlerts` | bool | Perfil (1.5) | Equipo |
| `policyMode` | string | Audit o enforce (7.2) | Seguridad |

---

## 12. Definición de terminado (fase 6)

- [ ] La matriz de la fase 0 muestra cada control como descrito, en código, desplegado y probado.
- [ ] Cinco perfiles RBAC y la identidad de la API probados con acceso permitido y denegado.
- [ ] TLS verificado por tramo; el puerto 80 registrado como limitación.
- [ ] Application Insights, diagnósticos y Activity Log llegando al workspace persistente.
- [ ] Seis alertas desplegadas y una de ellas provocada, recibida y atendida.
- [ ] Etiquetas en todos los recursos y grupos; presupuesto con sus tres avisos.
- [ ] Iniciativa de Policy con pruebas positiva y negativa; Deny activo solo tras validar.
- [ ] CI compila, analiza y escanea las plantillas sin errores.
- [ ] Las cinco inconsistencias de la sección 9 resueltas y documentadas.
