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

Los 22 recursos: red, PostgreSQL, Redis, App Service. **Los datos de la base de datos se van con
él**, así que cada sesión empieza con el esquema vacío.

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

Deben salir **22 recursos**, todos `Create`. Los dos `Unsupported` —la política de acceso y la
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

## 4. Lo que todavía NO está resuelto

**No hay forma de correr las migraciones contra este PostgreSQL.** El servidor está inyectado en
la VNet y no tiene punto de conexión público, así que ni una máquina local ni un runner de GitHub
lo alcanzan.

Para el punto de control no importa: `/health/ready` hace `SELECT 1` y no toca ninguna tabla.
**Para una demostración real sí**, porque sin `alembic upgrade head` y el seed el sistema arranca
sin materias, sin estudiantes y sin ventana de matrícula.

La solución prevista es un contenedor de un solo uso dentro de la VNet que ejecute las
migraciones y el seed, y muera. Cuesta céntimos. Está pendiente para la iteración D.

---

## 5. Destruir

```bash
az group delete --name matricula-demo --yes --no-wait
```

Tarda unos diez minutos y **no hay que esperarlo**. Deja de contar el gasto casi de inmediato.

**Nunca borrar `matricula-base`.** Si se borra por error, hay que rehacer `base.bicep` y volver a
crear los secretos, y el nombre del Key Vault queda bloqueado 90 días —habría que usar otro—.

---

## 6. Coste

| Perfil | USD/hora | Sesión de 6 h |
|---|---|---|
| Económico | ~0,06 | ~0,36 |
| Demostración (el del documento) | ~1,20 | ~7 |
| Grupo base, siempre encendido | — | ~5 USD/mes |

Con el crédito de 100 USD de Azure for Students caben varias sesiones de sustentación y muchas de
prueba, **siempre que el grupo efímero se destruya al terminar**.

---

## 7. Cosas que solo se descubren ejecutando

Quedan anotadas porque ninguna se ve desde el código y todas costaron un intento fallido:

1. **`eastus` está prohibida** por política de la suscripción.
2. **ACR Tasks está bloqueado**: la imagen se construye en local, no en Azure.
3. **Azure Cache for Redis está retirado.** Crear uno falla con «create Azure Managed Redis
   instance instead». Ya se migró a `Microsoft.Cache/redisEnterprise`, que además salió más
   barato: 0,018 USD/hora frente a 0,022.
4. **Un Key Vault con `accessPolicies: []` nace inservible.** Ser dueño de la suscripción no da
   acceso a los datos: hay que concederse la política explícitamente, y eso ya lo hace
   `base.bicep`.
