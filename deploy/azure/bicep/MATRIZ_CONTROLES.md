# Matriz de controles — secciones 10 a 15

Criterio de cierre de la sección 14: cada control con cuatro estados, cada estado con su evidencia.

- **Descrito**: lo exige el documento del proyecto (sección entre paréntesis).
- **En código**: está en Bicep o en los scripts. Evidencia: el archivo.
- **Probado (local)**: lo comprueba una prueba de `deploy/azure/pruebas/` sobre el ARM compilado,
  sin Azure. Evidencia: la prueba.
- **Desplegado** y **probado (Azure)**: pendientes hasta lanzar `desplegar-base.sh` y
  `levantar.sh`. Se rellenan con la evidencia de esa sesión.

Estado al 2026-10-29: **todo lo que es Bicep está en código y probado en local; nada está
desplegado todavía.**

## IAM y cifrado (10.1, 10.2, 10.3)

| Control | En código | Probado (local) | Desplegado | Probado (Azure) |
|---|---|---|---|---|
| Identidad de la API con un solo rol sobre el Key Vault (10.1) | `aplicacion/permisos.bicep` | `test_seguridad.IdentidadDeLaApi` | ☐ | ☐ `/health/ready` responde |
| Key Vault con RBAC, sin políticas de acceso (10.1) | `base.bicep` | `test_seguridad.KeyVault` | ☐ | ☐ |
| Secrets Officer fuera de Bicep (10.1) | RUNBOOK §1 | `test_seguridad.test_secrets_officer_no_esta_en_bicep` | — | ☐ asignación y retirada en el registro |
| Cinco perfiles a grupos de Entra (10.1) | `acceso/*.bicep`, `suscripcion.bicep` | `test_seguridad.PerfilesHumanos` | **Excepción** INFRASTRUCTURE §7.10 | ☐ al existir los grupos |
| Condición del RBAC Administrator (10.1) | `acceso/perfiles-grupo.bicep` | `test_la_delegacion_no_permite_escalar` | ☐ | ☐ |
| Registros de acceso al Key Vault (10.3) | `base.bicep` | `test_registro_de_auditoria` | ☐ | ☐ |
| App Service: HTTPS, TLS 1.2, sin FTPS (10.2) | `aplicacion/app.bicep` | `CifradoEnTransito.test_app_service` | ☐ | ☐ |
| PostgreSQL: TLS obligatorio, mínimo 1.2 (10.2) | `datos/postgres.bicep` | `test_postgres_tls_y_en_fila` | ☐ | ☐ conexión sin `sslmode` rechazada |
| Redis: TLS en el 10000 (10.2) | `datos/redis.bicep`, `red/red.bicep` | `test_redis`, `test_puertos_de_la_red` | ☐ | ☐ |
| Entrada por 80 | — | `test_sonda_del_gateway_por_443` | **Limitación** INFRASTRUCTURE §7.12 | — |

## Observabilidad y alertas (11.1, 11.2, 11.3)

| Control | En código | Probado (local) | Desplegado | Probado (Azure) |
|---|---|---|---|---|
| Application Insights sobre el workspace (11.1) | `monitoreo/telemetria.bicep` | `Telemetria` | ☐ | ☐ |
| Diagnósticos de API, plan, PostgreSQL y gateway (11.2) | `operacion/observabilidad.bicep` | `Diagnosticos` | ☐ | ☐ filas en cada tabla |
| Exportación del Registro de actividad (11.1) | `monitoreo/registro-actividad.bicep` | `RegistroDeActividad` | ☐ | ☐ consulta de 11.3 con resultados |
| Retención 30 / 90 días (11.2) | `base.bicep`, `monitoreo/telemetria.bicep` | `test_retencion_de_auditoria` | ☐ | ☐ |
| Grupo de acciones (11.2) | `monitoreo/grupo-acciones.bicep` | `test_grupo_de_acciones` | ☐ | ☐ |
| Alertas 1, 2, 3 y 6 (11.1) | `monitoreo/alertas-registros.bicep` + `consultas/*.kql` | `test_las_cuatro_alertas_de_logs`; consultas ejecutadas contra el workspace real (`test_consultas`) | ☐ | ☐ una provocada y recibida |
| Alerta 4, almacenamiento de PostgreSQL (11.1) | `datos/postgres.bicep` | `test_alerta_4_almacenamiento_en_el_grupo_efimero` | ☐ | ☐ |
| Alerta 5, permisos y políticas (11.1) | `monitoreo/alerta-actividad.bicep` | `test_alerta_5_permisos_y_politicas` | ☐ | ☐ dispara al rotar `jwt-secret` |
| Nombres vigilados = nombres creados | `comun/nombres.bicep` | `test_nombres` | — | — |

## Costos (12.2, 12.3)

| Control | En código | Probado (local) | Desplegado | Probado (Azure) |
|---|---|---|---|---|
| Cuatro etiquetas en todo recurso etiquetable (12.2) | `comun/etiquetas.bicep` y cada módulo | `test_etiquetas.EtiquetasEnTodo` | ☐ | ☐ |
| Etiquetas en los grupos (12.2) | `suscripcion.bicep`, `scripts/lib/despliegue.sh` | `test_scripts` (contra un `az` falso) | ☐ | ☐ |
| Presupuesto con tres avisos (12.3) | `costos/presupuesto.bicep` | `test_gobernanza.Presupuesto` | ☐ | ☐ |
| Rol FinOps (10.1, 12.3) | `suscripcion.bicep` | `test_asignaciones_a_grupos` | **Excepción** §7.10 | ☐ |

## Gobernanza (13.2, 13.3)

| Control | En código | Probado (local) | Desplegado | Probado (Azure) |
|---|---|---|---|---|
| Región restringida (13.2) | `@allowed(['centralus'])` en las tres entradas | `RegionRestringida` | ☐ | — |
| Iniciativa con las cinco reglas (13.3) | `gobernanza/iniciativa.bicep` | `test_gobernanza.Iniciativa` | ☐ | ☐ |
| Auditar antes de bloquear (13.3) | `gobernanza/asignacion.bicep`, `suscripcion.json` | `test_politicas_nacen_en_auditoria` | ☐ en `audit` | ☐ |
| Pruebas negativas (13.3) | `scripts/probar-politicas.sh`, `pruebas/politicas/` | `test_probar_politicas_se_niega_en_modo_auditoria` | — | ☐ evidencias en `deploy/azure/evidencias/` |

## Validación en CI (14)

| Control | Evidencia |
|---|---|
| Compilar todas las plantillas, sin avisos | `scripts/validar.sh` §1, job `iac-ci` |
| Pruebas sobre el ARM compilado | `scripts/validar.sh` §2 |
| shellcheck de los scripts | `scripts/validar.sh` §3 |
| Escaneo de secretos | gitleaks del job `backend-ci`, sobre todo el repositorio |
| `what-if` solo con credenciales | `ci.yml`, condicionado a `AZURE_CREDENTIALS` |
