# Infraestructura como código

La infraestructura de `INFRASTRUCTURE.md`, declarada en Bicep. **Esto sí aprovisiona**, al
contrario que el `README.md` del directorio padre, que solo documenta la configuración que el
backend espera encontrar.

## Por qué esto existe

El proyecto es académico y vive de un crédito de estudiante. La arquitectura del documento
cuesta unos **250 USD al mes**, pero **menos de 10 USD por una sesión de seis horas**. El
problema nunca fue el recurso: fue dejarlo encendido.

De ahí que la infraestructura sea código. Destruirla y recrearla solo es razonable si es un
comando; con cuarenta minutos de clics en el portal cada vez, nadie la destruye y el crédito se
agota en tres semanas.

## Dos grupos de recursos

```
matricula-base   ACR y Key Vault. ~5 USD/mes. NUNCA se borra.
matricula-demo   todo lo que declara main.bicep. Se crea y se destruye.
```

**El Key Vault va fuera porque tiene borrado lógico de 90 días.** Si se destruyera con el resto,
su nombre quedaría reservado y el segundo despliegue fallaría con «name already in use», sin
mencionar en ningún momento que el recurso está en la papelera. Es el fallo que hace que un
montaje funcione una vez y a la siguiente no.

**El ACR va fuera porque guarda las imágenes.** Si se borrara, cada sesión empezaría
reconstruyendo y subiendo la imagen antes de que el App Service pudiera arrancar.

## Qué se despliega

**`base.bicep`** sobre el grupo persistente: ACR y Key Vault. Una vez y para siempre.

**`main.bicep`** sobre el grupo efímero, 22 recursos:

| Recurso | Detalle |
|---|---|
| VNet `10.0.0.0/16` | Cuatro subredes, con NSG cada una |
| NAT Gateway + IP pública | Salida con dirección fija desde la subred de la aplicación |
| PostgreSQL Flexible Server | Inyectado en subred delegada, sin acceso público, con réplica en otra zona |
| Azure Cache for Redis | Basic C0, TLS obligatorio, con punto de conexión privado |
| Dos zonas DNS privadas | Sin ellas los nombres resuelven a direcciones públicas cerradas |
| App Service Plan + Web App | Contenedor Linux, identidad administrada, integrado en la VNet |
| Dos secretos en el Key Vault | `database-url` y `redis-url`, escritos en el grupo persistente |
| Permisos | Lectura del almacén y descarga del ACR para la identidad |

Pendiente: autoescalado y Application Gateway (iteración C).

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

## El único secreto que Bicep NO escribe

`database-url` y `redis-url` apuntan a servidores que se crean de cero cada vez, así que los
escribe el despliegue. **`jwt-secret` no.** Es la clave con la que se firman las sesiones:
regenerarla en cada despliegue invalidaría todos los tokens emitidos.

Se crea **una sola vez**, a mano, en el grupo persistente:

```bash
az keyvault secret set --vault-name <almacen> --name jwt-secret   --value "$(openssl rand -base64 48)"
```

## Un permiso que puede faltar

`permisos.bicep` concede dos cosas, y no son iguales:

- **Leer secretos del Key Vault**: es una política de acceso, y basta con ser dueño del almacén.
- **Descargar del ACR (`AcrPull`)**: es una asignación de rol, y **exige permiso de Owner o de
  User Access Administrator sobre la suscripción**.

Si el despliegue falla con `AuthorizationFailed`, esa es la causa. La salida es habilitar el
usuario administrador del ACR y pasar sus credenciales por configuración, al precio de dejar una
contraseña de registro donde la lee cualquiera con permiso de lectura.

## Tres cosas del documento que no se traducen literales

**1. La «subred de respaldo» para el standby no existe.** La alta disponibilidad con redundancia
de zona coloca la réplica en otra zona de disponibilidad usando la MISMA subred delegada. El
cuarto rango se usa para puntos de conexión privados, que sí necesitan subred propia porque la
de PostgreSQL está delegada en exclusiva.

**2. Redis escucha en el 6380 con TLS, no en el 6379.** Azure Cache deshabilita el puerto sin
cifrar. `REDIS_URL` empieza por `rediss://`.

**3. «App Gateway → App: 8000» no aplica.** El 8000 es el puerto interno del contenedor
(`WEBSITES_PORT`); App Service publica por 443. El aislamiento se consigue con restricciones de
acceso, no abriendo un puerto.

**Y una cuarta, la que decide el coste:** la alta disponibilidad **no existe en el nivel
Burstable**. `INFRASTRUCTURE.md` pide «B1ms + standby» y son mutuamente excluyentes. Por eso hay
dos archivos de parámetros.

## La región no se elige libremente

**La suscripción de estudiante tiene una política que restringe dónde se puede desplegar**, y es
lo primero que hay que saber: intentar `eastus` falla con `RequestDisallowedByAzure` después de
haber escrito la plantilla entera. El mensaje habla de «best available regions» y no dice cuáles
son.

Se consultan así:

```bash
az policy assignment list --disable-scope-strict-match --query "[0].parameters"
```

En esta suscripción son cinco, y **solo cuatro sirven**:

| Región | Zonas | ¿Vale? |
|---|---|---|
| `centralus` | 3 | **Sí — la elegida** |
| `canadacentral` | 3 | Sí |
| `brazilsouth` | 3 | Sí, pero más cara |
| `chilecentral` | 3 | Sí, pero más cara |
| `northcentralus` | **0** | **No**: sin zonas de disponibilidad, la réplica de PostgreSQL no se puede activar |

Se eligió `centralus` por tener las tres zonas y precios de Estados Unidos. Las regiones
latinoamericanas están más cerca de Medellín, pero el sobreprecio pesa más que la latencia cuando
el presupuesto es un crédito de estudiante.

Si la política cambia o se usa otra suscripción, hay que repetir la consulta antes de desplegar.

## Los dos archivos de parámetros

| | Nivel | Réplica | Coste aproximado |
|---|---|---|---|
| `parametros.demo.json` | GeneralPurpose `D2ds_v4` | **sí** | ~0,36 USD/hora |
| `parametros.economico.json` | Burstable `B1ms` | no | ~0,022 USD/hora |

El económico sirve para probar el despliegue sin gastar; el de demostración es el que cumple el
documento y el que se usa para sustentar.

## Cómo se ejecuta

Los comandos van con la CLI de Azure. **Las plantillas ya están validadas contra Azure**:
`az bicep build` compila los seis archivos sin advertencias, `az deployment group validate` pasa
con los dos perfiles, y `what-if` anuncia los 22 recursos esperados. Lo que todavía no se ha
hecho es aplicarlas.

`what-if` marca como `Unsupported` la política de acceso y la asignación de rol. **No es un
error**: son recursos cuyo nombre se calcula en tiempo de despliegue y la previsualización no
sabe resolverlos.

```bash
# 1. Iniciar sesión y fijar la suscripción
az login
az account set --subscription "<tu suscripción>"

# 2. Los proveedores tienen que estar registrados, o el despliegue falla al minuto
az provider register --namespace Microsoft.DBforPostgreSQL --wait
az provider register --namespace Microsoft.Cache --wait
az provider register --namespace Microsoft.Network --wait

# 3a. El grupo PERSISTENTE, una sola vez en la vida del proyecto
az group create --name matricula-base --location centralus
az deployment group create --resource-group matricula-base --template-file base.bicep

#     y el secreto que Bicep no escribe, también una sola vez
az keyvault secret set --vault-name <el que devolvio el paso anterior>   --name jwt-secret --value "$(openssl rand -base64 48)"

# 3b. El grupo efímero
az group create --name matricula-demo --location centralus

# 4. VER qué haría, sin hacerlo. Nunca se aplica nada sin mirar esto antes.
#    `validate` comprueba que Azure acepta la plantilla; `what-if` dice qué crearía.
az deployment group what-if \
  --resource-group matricula-demo \
  --template-file main.bicep \
  --parameters @parametros.demo.json \
  --parameters claveAdminPostgres="<la clave>"

# 5. Aplicarlo. Unos 40 minutos.
az deployment group create \
  --resource-group matricula-demo \
  --template-file main.bicep \
  --parameters @parametros.demo.json \
  --parameters claveAdminPostgres="<la clave>"

# 6. Al terminar la sesión de pruebas
az group delete --name matricula-demo --yes --no-wait
```

**La contraseña se pasa por línea de comandos y no vive en ningún archivo de parámetros.** En
cuanto exista el Key Vault persistente, se leerá de ahí y desaparecerá también del historial de
la terminal.

## Cuánto tarda, y por qué importa

Unos **cuarenta minutos**. Redis ronda los veinte por su cuenta y PostgreSQL con alta
disponibilidad otros quince; Bicep los crea en paralelo pero no puede acelerarlos.

**No se lanza cinco minutos antes de sustentar.**

## Los datos no sobreviven

Destruir el grupo se lleva la base de datos entera. Cada sesión empieza con el esquema vacío, así
que después de cada despliegue hay que correr las migraciones y el seed:

```bash
alembic upgrade head
python -m app.infrastructure.seed
```

El seed es idempotente y crea materias, estudiantes, docentes y una ventana de matrícula. Sin ese
paso el sistema arranca sin nada que enseñar.
