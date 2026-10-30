# Infraestructura como código

La infraestructura de `INFRASTRUCTURE.md`, declarada en Bicep, más lo que exigen las secciones 10
a 15 del documento del proyecto (IAM, cifrado, observabilidad, alertas, costos y gobernanza).
**Esto sí aprovisiona**, al contrario que el `README.md` del directorio padre, que documenta el
camino manual que estas plantillas sustituyeron.

Para operarla, el sitio es `../RUNBOOK.md`. Esto explica cómo está hecha.

## Por qué esto existe

El proyecto es académico y vive de un crédito de estudiante. La arquitectura del documento
cuesta unos **250 USD al mes**, pero **menos de 10 USD por una sesión de seis horas**. El
problema nunca fue el recurso: fue dejarlo encendido.

De ahí que la infraestructura sea código. Destruirla y recrearla solo es razonable si es un
comando; con cuarenta minutos de clics en el portal cada vez, nadie la destruye y el crédito se
agota en tres semanas.

## Tres plantillas de entrada, tres ámbitos

| Plantilla | Ámbito | Ciclo de vida | Qué declara |
|---|---|---|---|
| `base.bicep` | grupo `matricula-base` | **Persistente** | ACR, Key Vault (RBAC), workspace, Application Insights, grupo de acciones, alertas 1, 2, 3, 5 y 6, perfiles RBAC del grupo |
| `suscripcion.bicep` | suscripción | **Persistente** | Etiquetas del grupo base, exportación del Registro de actividad, presupuesto, iniciativa de Policy y su asignación, rol FinOps |
| `main.bicep` | grupo `matricula-demo` | **Efímero** | Red, datos, aplicación, borde, autoescalado, migraciones, diagnósticos, alerta 4, perfiles RBAC de recursos |

Se despliegan en ese orden: `base` → `suscripcion` → `main`. Las dos primeras las lanza
`scripts/desplegar-base.sh`, la tercera `scripts/levantar.sh`. `main` lee de `base` Application
Insights y el grupo de acciones; `suscripcion`, el workspace y el grupo de acciones.

**El Key Vault va en lo persistente porque tiene borrado lógico de 90 días.** Si se destruyera con
el resto, su nombre quedaría reservado y el segundo despliegue fallaría con «name already in use»,
sin mencionar en ningún momento que el recurso está en la papelera.

## Cómo están organizados los módulos

Un dominio por carpeta. Las plantillas de entrada solo componen, y donde un dominio tiene varias
plantillas, una de ellas compone a las demás.

| Carpeta | Plantilla | Qué hace |
|---|---|---|
| `modules/comun/` | `etiquetas.bicep` | El objeto de etiquetas de 12.2 y los valores válidos de `Ambiente`. **Sin recursos**: solo exporta |
| | `nombres.bicep` | Los nombres de todo lo que otro grupo necesita encontrar. **Sin recursos** |
| | `roles.bicep` | Los GUID de los roles integrados y el tipo de los grupos de Entra. **Sin recursos** |
| `modules/red/` | `red.bicep` | VNet, cinco subredes con su NSG, y el NAT opcional |
| `modules/datos/` | `datos.bicep` | **Compone** los tres siguientes; es el único que conoce las dos mitades de cada cadena de conexión |
| | `postgres.bicep` | Flexible Server en subred delegada, zona DNS, extensiones, TLS 1.2 obligatorio y la alerta 4 |
| | `redis.bicep` | Managed Redis por TLS en el 10000, su base, el punto de conexión privado y su zona DNS |
| | `secretos.bicep` | Escribe `database-url` y `redis-url` en el Key Vault persistente |
| `modules/aplicacion/` | `app.bicep` → `permisos.bicep` → `ajustes.bicep` | El orden obligatorio que se explica más abajo |
| `modules/acceso/` | `perfiles-grupo.bicep` | Los perfiles humanos de 10.1 con ámbito de grupo, condicionados a que exista su grupo de Entra |
| | `perfiles-recursos.bicep` | Los del perfil de desarrollo, sobre la API y la cuenta del frontend |
| `modules/operacion/` | `escalado.bicep` | Reglas de autoescalado (solo con S1) |
| | `migraciones.bicep` | El contenedor de un solo uso que escribe el esquema dentro de la VNet |
| | `observabilidad.bicep` | Diagnósticos de la API, el plan, PostgreSQL y el gateway hacia el workspace |
| `modules/monitoreo/` | `telemetria.bicep` | Application Insights sobre el workspace y la retención por tabla |
| | `grupo-acciones.bicep` | A quién avisan las alertas |
| | `alertas-registros.bicep` | Las alertas 1, 2, 3 y 6, con sus consultas en `consultas/*.kql` |
| | `alerta-actividad.bicep` | La alerta 5: cambios de permisos o de políticas |
| | `registro-actividad.bicep` | Exporta el Registro de actividad de la suscripción |
| `modules/costos/` | `presupuesto.bicep` | El presupuesto mensual con sus tres avisos. Avisa, no detiene |
| `modules/gobernanza/` | `iniciativa.bicep` | Las cinco reglas de 13.3: definiciones, sin aplicar nada |
| | `asignacion.bicep` | Dónde y en qué modo se aplican: `audit` o `enforce` |
| `modules/borde/` | `borde.bicep` | **Compone** los dos siguientes; se enciende con `desplegarBorde` |
| | `gateway.bicep` | IP pública, política WAF y Application Gateway |
| | `frontend.bicep` | La cuenta de almacenamiento del sitio estático |

**Por qué existe `comun/nombres.bicep`.** Las alertas viven en el grupo persistente y vigilan
recursos efímeros por su identificador. No pueden leer salidas de un despliegue que todavía no
existe, y escribir los nombres a mano los dejaría desactualizados el día que alguien cambie uno.
Con la función compartida, `main.bicep` crea y `base.bicep` vigila con el MISMO cálculo. Funciona
porque los nombres son deterministas: el sufijo es `uniqueString` del identificador del grupo.

**PostgreSQL y Redis van en módulos separados y sin dependencia entre sí**, así que Bicep los crea
en paralelo: son los dos recursos más lentos del despliegue. La clave de Redis no sale como salida
de `redis.bicep` —quedaría en el historial del grupo—: `datos.bicep` la lee con `listKeys` sobre
un recurso `existing`.

## El orden de la aplicación, que es lo más frágil de todo

    plan  ->  aplicación  ->  permisos  ->  ajustes

La primera versión metía los ajustes dentro de `app.bicep` con un `dependsOn` hacia los
permisos, y **el compilador la rechazó por un ciclo que era real**: los permisos necesitan el
`principalId` de la identidad administrada, que no existe hasta que la aplicación se crea.

Por eso los ajustes viven en `ajustes.bicep`. Y el orden importa porque las referencias
`@Microsoft.KeyVault(SecretUri=...)` las resuelve App Service AL APLICAR la configuración: si en
ese momento la identidad no tiene permiso, no falla — guarda la **cadena literal**
`@Microsoft.KeyVault(...)` como valor de `DATABASE_URL`. El síntoma es un error de PostgreSQL
sobre una URL malformada, sin mención alguna al almacén ni a los permisos.

## Los permisos

`permisos.bicep` da a las identidades administradas lo justo, y todo es RBAC:

- **La API**: *Key Vault Secrets User* sobre el almacén —leer secretos, nada más— y `AcrPull`.
- **Las migraciones**: solo `AcrPull`. La cadena de conexión le llega como variable segura.

Los cinco perfiles HUMANOS de 10.1 van en `modules/acceso/` y se asignan a grupos de Entra, nunca
a usuarios. **Hoy no se asigna ninguno**: la cuenta del proyecto no puede crear grupos en el
directorio de la universidad, así que sus identificadores van vacíos y cada asignación se omite.
Es una excepción registrada en `INFRASTRUCTURE.md` §7.

El *RBAC Administrator* del perfil de seguridad lleva una **condición** que limita los roles que
puede delegar a la lista de la tabla de 10.1, sin Contributor, Owner ni a sí mismo: sin ella,
quien lo tenga podría darse más poder del que tiene.

*Key Vault Secrets Officer* **no está en Bicep** a propósito (10.1): se asigna un momento para
escribir `jwt-secret` y se retira. El procedimiento está en el RUNBOOK.

## Los archivos de parámetros

| Archivo | Plantilla | Qué lleva |
|---|---|---|
| `parametros/economico.json` | `main.bicep` | PostgreSQL Burstable `B1ms`, sin réplica ni borde. `Ambiente: dev` |
| `parametros/demo.json` | `main.bicep` | `D2ds_v4` con réplica, S1 con autoescalado, gateway con WAF, alerta 4. `Ambiente: demo` |
| `parametros/base.json` | `base.bicep` | Purga del Key Vault, correos de las alertas, retenciones |
| `parametros/suscripcion.json` | `suscripcion.bicep` | Presupuesto y modo de la gobernanza |
| `parametros/etiquetas.json` | **las tres** | `dueno` y `centroCosto`, un solo sitio para un valor que va en todo |

**Los valores del equipo van vacíos** —`dueno`, `centroCosto`, los correos y el presupuesto—
porque el documento prohíbe inventarlos (14). Las plantillas los declaran con `@minLength(1)` o
`@minValue(1)`, y los scripts se niegan a arrancar mientras falten.

**La etiqueta `Ambiente` no es el ambiente de la aplicación.** `ambiente` llega al backend como
`ENVIRONMENT`, y con `dev` el backend escribe los logs en texto plano. La etiqueta va en
`etiquetaAmbiente`.

## Lo que no se traduce literal del documento

**1. La «subred de respaldo» para el standby no existe.** La alta disponibilidad con redundancia
de zona coloca la réplica en otra zona de disponibilidad usando la MISMA subred delegada. No hay
propiedad para ponerla en otra subred; lo que sí podría ir en otra es una réplica de LECTURA, que
es otro servidor. Se corrige el diagrama, no el Bicep.

**2. Redis escucha en el 10000 con TLS**, no en el 6379 del documento original ni en el 6380 del
servicio retirado. `REDIS_URL` empieza por `rediss://`.

**3. «App Gateway → App: 8000» no aplica.** El 8000 es el puerto interno del contenedor
(`WEBSITES_PORT`); App Service publica por 443.

**4. La entrada por el puerto 80 sigue en HTTP** (10.2). Queda registrada como limitación: no hay
certificado ni dominio propio para terminar TLS en el gateway.

**5. Las alertas 2 y 6 leen `AppServiceHTTPLogs`, no `AppRequests`.** La API todavía no envía
telemetría a Application Insights; sobre `AppRequests` estarían desplegadas y mudas.

**Y la que decide el coste:** la alta disponibilidad **no existe en el nivel Burstable**.
`INFRASTRUCTURE.md` pide «B1ms + standby» y son mutuamente excluyentes. Por eso hay dos perfiles.

## La región no se elige libremente

`ubicacion` solo admite `centralus` (`@allowed`), por dos razones que se suman:

- **13.2**: Estados Unidos figura entre los países con nivel adecuado de protección de la Circular
  Externa 005 de 2017 de la SIC. Añadir otra región solo si su país está en esa lista.
- **La suscripción de estudiante** restringe dónde se puede desplegar, y de sus cinco regiones
  `northcentralus` no tiene zonas de disponibilidad: la réplica de PostgreSQL no se activaría.

```bash
az policy assignment list --disable-scope-strict-match --query "[0].parameters"
```

## Cómo se comprueba sin tocar Azure

```bash
./deploy/azure/scripts/validar.sh
```

Compila las 34 plantillas —un aviso del compilador es un fallo—, pasa shellcheck a los scripts y
ejecuta `deploy/azure/pruebas/`: 66 pruebas sobre el ARM compilado que comprueban lo que exige el
documento, de los parámetros a la gobernanza, más el flujo real de los scripts contra un `az`
falso. Las consultas de las alertas se ejecutan contra el workspace real con
`FLEXGRADE_PRUEBAS_AZURE=1`, que solo lee.

## Cuánto tarda, y por qué importa

Unos **cuarenta minutos** la demo. Redis ronda los veinte por su cuenta y PostgreSQL con alta
disponibilidad otros quince; Bicep los crea en paralelo pero no puede acelerarlos. Lo persistente,
un par de minutos.

**No se lanza cinco minutos antes de sustentar.**
