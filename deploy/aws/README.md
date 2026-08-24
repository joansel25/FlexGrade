# Despliegue en AWS — lo que el backend espera encontrar

Esta carpeta contiene lo que hay que darle a AWS para que el backend arranque, y la lista de
comprobaciones para saber si quedó bien. **No aprovisiona nada**: la infraestructura se crea
desde la consola de AWS o con la CLI; aquí solo vive lo que el repositorio aporta.

## 1. `Dockerrun.aws.json` — el archivo que Elastic Beanstalk lee

Elastic Beanstalk, en su plataforma Docker, no construye la imagen: la **descarga** de un
registro. `Dockerrun.aws.json` es el archivo donde le dices cuál y en qué puerto escucha.

Los dos valores en mayúsculas son marcadores que el pipeline sustituye antes de subir el
paquete, para que la etiqueta de imagen corresponda exactamente al commit desplegado:

```bash
sed -e "s|REEMPLAZAR_ECR_REPOSITORY|${ECR_REPOSITORY}|" \
    -e "s|REEMPLAZAR_IMAGE_TAG|${IMAGE_TAG}|" \
    deploy/aws/Dockerrun.aws.json > Dockerrun.aws.json
zip -r deploy.zip Dockerrun.aws.json
```

`"HostPort": 80` es lo que conecta las piezas: el proxy de la instancia escucha en el 80 y
reenvía al 8000 del contenedor, que es donde uvicorn está atendiendo.

## 2. Variables de entorno del ambiente

Se configuran en Elastic Beanstalk (**Configuration → Software → Environment properties**), y
las sensibles se leen de AWS Secrets Manager. La imagen es la misma en todos los ambientes: lo
único que cambia es esta configuración.

| Variable | Obligatoria | Valor en la nube |
|---|---|---|
| `DATABASE_URL` | sí | `postgresql+psycopg://usuario:clave@<endpoint-rds>:5432/matricula` |
| `REDIS_URL` | sí | `redis://<endpoint-elasticache>:6379/0`, o `rediss://` si activas cifrado en tránsito |
| `JWT_SECRET` | sí | distinto por ambiente; nunca se reutiliza entre dev, staging y prod |
| `CORS_ALLOWED_ORIGINS` | sí, en cuanto exista el frontend | el dominio de CloudFront, p. ej. `https://d1234.cloudfront.net` |
| `ENVIRONMENT` | recomendable | `dev`, `staging` o `prod`. Distinto de `dev` activa los logs en JSON |
| `DOCS_ENABLED` | recomendable | `false` en producción |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | según instancia | ver el apartado 4 |
| `LOG_LEVEL` | opcional | `INFO` |
| `APP_VERSION` | opcional | la etiqueta del despliegue, para verla en `/health` |

Si falta alguna de las tres primeras, **la aplicación no arranca**: falla al iniciar con un
error explícito en vez de comportarse de forma rara en caliente. Es deliberado, y en un
despliegue es la diferencia entre enterarte en el minuto uno o cuando entra el primer estudiante.

## 3. Health checks del balanceador

| Ruta | Qué comprueba | Para qué sirve |
|---|---|---|
| `/health` | que el proceso responde | **Esta es la que debe usar el ALB** (Configuration → Load balancer → Health check path) |
| `/health/ready` | además, que PostgreSQL y Redis responden | Verificación posterior al despliegue, a mano o desde el pipeline |

**No pongas `/health/ready` en el ALB.** Si lo haces, una caída momentánea de RDS hará que el
balanceador retire instancias que están sanas, el autoescalado las reemplace por otras que
fallarán igual, y un incidente de base de datos se convierta en una caída total.

Después de cada despliegue, la comprobación que de verdad dice si quedó bien configurado:

```bash
curl -s https://<tu-entorno>.elasticbeanstalk.com/health/ready | jq
# {"status":"ready","dependencies":{"postgres":"ok","redis":"ok"}}
```

`redis: "degraded"` no es un fallo de despliegue: la aplicación funciona sin caché, solo más
lenta. `postgres: "error"` sí lo es, y viene con un `503`.

## 4. Conexiones contra RDS — la cuenta que hay que hacer

Es el error de dimensionamiento más común y no da la cara hasta el pico.

Cada instancia mantiene hasta `DB_POOL_SIZE + DB_MAX_OVERFLOW` conexiones. Con los valores por
defecto son 30 por instancia. Una `db.t3.micro` admite unas 87 conexiones en total, así que:

```
4 instancias × 30 = 120 conexiones  >  87 disponibles  →  "too many connections"
```

Y ocurriría justo cuando el autoescalado sube instancias, es decir, en plena matrícula. Dos
salidas, y no son excluyentes: bajar `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` en las propiedades del
ambiente, o usar una instancia de RDS mayor. Por eso son variables de entorno y no constantes
en el código: se ajustan sin reconstruir ni redesplegar la imagen.

## 5. Grupos de seguridad — quién habla con quién

Es lo que hace real el aislamiento de la VPC del documento del proyecto:

- **ALB**: acepta 80/443 desde internet.
- **Instancias de la aplicación**: aceptan tráfico **solo desde el grupo de seguridad del ALB**,
  nunca desde `0.0.0.0/0`.
- **RDS**: acepta 5432 **solo desde el grupo de las instancias**.
- **ElastiCache**: acepta 6379 **solo desde el grupo de las instancias**.

Si RDS o ElastiCache aceptan tráfico desde cualquier sitio, la subred privada deja de proteger
nada: es la configuración por defecto más peligrosa de todo el montaje.

## 6. Migraciones

Alembic corre **antes** de que las instancias nuevas reciban tráfico, como paso del pipeline y
una sola vez por despliegue —no una vez por instancia—:

```bash
alembic upgrade head
```

Nunca se revierte una migración automáticamente, y un cambio destructivo va en dos releases
(`CI_CD.md` sección 6). El contenedor no las ejecuta al arrancar: si lo hiciera, cinco
instancias arrancando a la vez lanzarían cinco migraciones simultáneas sobre la misma base.

## 7. Logs en CloudWatch

El contenedor escribe JSON a stdout, una línea por evento; el agente de la instancia lo entrega
a CloudWatch Logs. Hay que activarlo en Elastic Beanstalk: **Configuration → Software → Log
streaming → Enabled**. Sin eso, los registros mueren con la instancia cuando el autoescalado la
retira.

Consultas útiles en CloudWatch Logs Insights:

```
fields @timestamp, path, status_code, duration_ms
| filter status_code >= 500
| sort @timestamp desc

fields @timestamp, path, duration_ms
| filter duration_ms > 1000
| sort duration_ms desc
```

Cada respuesta lleva la cabecera `X-Request-ID`. Cuando alguien reporte un fallo concreto, ese
valor encuentra la línea exacta:

```
fields @timestamp, @message | filter request_id = "el-valor-reportado"
```
