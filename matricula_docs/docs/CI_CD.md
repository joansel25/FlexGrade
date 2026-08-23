# Integración y despliegue continuos (CI/CD)

Este documento define el pipeline de integración y despliegue continuos del Sistema de Matrícula Académica. Cada push al repositorio dispara una cadena automatizada de validaciones y, según la rama, un despliegue al entorno correspondiente.

## 1. Filosofía

El pipeline se construye alrededor de tres principios:

1. **Automatizar todo lo que se hace más de una vez.** Los tests, el linting, la construcción de imágenes y el despliegue no deben depender de que un humano se acuerde.
2. **Fallar rápido y visible.** Un error debe interrumpir el pipeline en el primer paso donde se detecta, no seguir consumiendo recursos ni ocultarse en logs.
3. **El main siempre debe ser desplegable.** Ninguna rama merge a main si el pipeline no está verde.

## 2. Herramienta: GitHub Actions

Se elige GitHub Actions por integración nativa con el repositorio, generoso tier gratuito para proyectos académicos y sintaxis declarativa en YAML. Los workflows viven en `.github/workflows/` en la raíz del repositorio.

## 3. Estrategia de ramas y ambientes

| Rama | Propósito | Ambiente de despliegue | Automático |
|---|---|---|---|
| `feature/*` | Desarrollo de una funcionalidad | Ninguno (solo CI) | Sí (CI) |
| `fix/*` | Corrección de bug | Ninguno (solo CI) | Sí (CI) |
| `develop` | Integración continua | `dev` (Elastic Beanstalk) | Sí |
| `main` | Código productivo estable | `staging` y luego `prod` | Sí a staging, manual a prod |

El flujo típico:

```
feature/enrollment-endpoint
        │
        │ Pull Request
        ▼
     develop ─────► despliegue automático a DEV
        │
        │ Pull Request (release)
        ▼
       main ──────► despliegue automático a STAGING
                    despliegue a PROD con aprobación manual
```

## 4. Workflows definidos

### 4.1 `ci.yml` — Integración continua (todas las ramas)

Se ejecuta en cada push y en cada pull request. No despliega nada, solo valida.

**Trabajo `backend-ci`:**

1. **Checkout** del código.
2. **Setup de Python 3.12** con caché de dependencias.
3. **Instalar dependencias** (`pip install -e ".[dev]"`).
4. **Linting**: `black --check`, `isort --check-only`, `mypy app`.
5. **Tests unitarios**: `pytest -m unit --cov=app/domain --cov=app/application --cov-fail-under=90`.

   El umbral se aplica sobre el **núcleo**, no sobre toda la aplicación. Medir `--cov=app` con solo los tests unitarios cuenta como no cubiertos los adaptadores de `infrastructure/`, que se prueban con tests de integración contra Postgres y Redis reales porque es la única forma de obtener una señal veraz sobre ellos. Con ese planteamiento, cada adaptador nuevo hundía la cifra global sin que faltara un solo test, y el gate acababa fallando por su propio diseño en vez de por un defecto del código.

   `domain` y `application` sí deben estar cubiertos por completo: ahí viven las reglas de negocio —cupos, prerrequisitos, choques de horario, vigencia del período— y no dependen de nada externo, así que no hay excusa para no probarlas de forma aislada y rápida. `infrastructure/` e `interfaces/` los garantizan los pasos de integración y e2e, que son funcionales: comprueban que el adaptador cumple lo que promete, no cuántas de sus líneas se ejecutaron.

   Los módulos de `application/ports/` quedan fuera de la medición (`omit` en `pyproject.toml`). Son contratos abstractos sin una línea de comportamiento, y su cobertura es binaria: 0% mientras nadie importe el módulo y 100% en cuanto alguien lo hace. Mide si se importó, no si está bien probado.
6. **Tests e2e en proceso**: `pytest -m e2e`. Paso provisional: los e2e corren con `TestClient` contra la app en el propio runner. Su destino final es el trabajo `e2e` de `deploy-staging.yml`, apuntando a la URL de STAGING; cuando ese trabajo se active, este paso se elimina.
7. **Migraciones de la base de pruebas**: `alembic upgrade head`. Sin este paso la base del runner está vacía y los tests de integración fallarían con `relation does not exist`. Se usa Alembic —y no un `create_all`— para ejercitar en CI el mismo camino que corre en DEV, STAGING y PROD.
8. **Tests de integración**: `pytest -m integration` (con Postgres y Redis levantados como servicios de GitHub Actions).
9. **Escaneo de seguridad**: `pip-audit` para detectar dependencias vulnerables.
10. **Escaneo de secretos**: `gitleaks` para detectar credenciales filtradas en el diff.

**Trabajo `frontend-ci`:**

1. Checkout del código.
2. Setup de Node 20.
3. `npm ci` (instalación reproducible).
4. `npm run lint` y `npm run type-check`.
5. `npm test -- --coverage`.
6. `npm run build` para validar que compile.

**Trabajo `docker-build`:** solo en pull requests hacia `develop` o `main`.

1. Construir la imagen de Docker (backend).
2. Ejecutar `docker scout` para detectar vulnerabilidades en la imagen.

Si cualquier trabajo falla, el pipeline se detiene y el PR no se puede mergear (regla de protección de rama).

### 4.2 `deploy-dev.yml` — Despliegue a Desarrollo

Se dispara automáticamente en cada push a `develop`.

1. Correr todo el `ci.yml` primero.
2. Construir la imagen Docker con tag `dev-<commit_sha>`.
3. Subir la imagen al **Amazon ECR** (repositorio privado).
4. Ejecutar migraciones de Alembic contra la base de datos de DEV.
5. Desplegar en **Elastic Beanstalk** ambiente `matricula-dev`.
6. Ejecutar smoke tests (health check + endpoints básicos).
7. Notificar el resultado a Slack o email.

### 4.3 `deploy-staging.yml` — Despliegue a Staging

Se dispara automáticamente en cada push a `main`.

Igual que `deploy-dev.yml`, pero contra el ambiente `matricula-staging` y con la etiqueta `staging-<commit_sha>`.

Después del despliegue se ejecuta una **suite E2E completa** contra staging, para validar que la integración funciona antes de considerar el release apto para producción.

### 4.4 `deploy-prod.yml` — Despliegue a Producción

Se dispara **manualmente** desde la interfaz de GitHub Actions (`workflow_dispatch`) y requiere:

1. Que el commit ya esté desplegado en staging y haya pasado los E2E.
2. **Aprobación manual** de un revisor autorizado (GitHub Environments).
3. Ejecutar migraciones en producción con `--sql` primero (dry-run) para revisión.
4. Desplegar con **estrategia rolling** (Elastic Beanstalk actualiza instancias por lotes).
5. Health checks post-despliegue.
6. Registrar el release en un tag `v<version>` de Git.

### 4.5 `rollback-prod.yml` — Rollback de Producción

Workflow manual para emergencias. Recibe como input la versión previa (tag Git o SHA) y:

1. Redespliega esa versión en Elastic Beanstalk.
2. Advierte si hay migraciones de BD que requieran rollback manual (Alembic no las revierte automáticamente en la mayoría de los casos).
3. Notifica el rollback ejecutado.

## 5. Pipeline completo, visualizado

```
    ┌──────────────────────┐
    │  git push feature/x  │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │       ci.yml         │  lint + tests + security scan
    └──────────┬───────────┘
               │  (verde)
               ▼
    ┌──────────────────────┐
    │  Pull Request a dev  │
    └──────────┬───────────┘
               │  (aprobado + verde)
               ▼
    ┌──────────────────────┐
    │  Merge a develop     │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │   deploy-dev.yml     │  → Ambiente DEV en AWS
    └──────────┬───────────┘
               │  (validado por el equipo)
               ▼
    ┌──────────────────────┐
    │ Pull Request a main  │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │   Merge a main       │
    └──────────┬───────────┘
               │
               ▼
    ┌──────────────────────┐
    │ deploy-staging.yml   │  → Ambiente STAGING + E2E
    └──────────┬───────────┘
               │  (E2E verde + aprobación manual)
               ▼
    ┌──────────────────────┐
    │  deploy-prod.yml     │  → Producción con rolling deploy
    └──────────────────────┘
```

## 6. Manejo de la base de datos en despliegues

Las migraciones son la parte más delicada del CI/CD porque tocan datos reales. Reglas:

- **Migraciones siempre hacia adelante.** Ningún deploy revierte una migración automáticamente.
- **Compatibilidad backward de un release.** Un release nuevo debe funcionar con el esquema del release anterior (para permitir rolling deploys sin downtime).
- **Cambios destructivos en dos fases.** Si hay que eliminar una columna: primero un release deja de escribirla, después otro release la elimina. Nunca en un solo commit.
- **Ejecución antes del deploy de la aplicación.** Alembic corre antes de que las instancias nuevas reciban tráfico.

## 7. Manejo de secretos

**Nunca se comitean secretos.** El pipeline los obtiene de:

- **GitHub Secrets** para credenciales necesarias durante el pipeline (AWS keys, Slack webhooks, tokens de Docker registry). Se configuran en `Settings → Secrets and variables → Actions`.
- **AWS Secrets Manager** para credenciales que consume la aplicación en runtime (DB password, JWT secret). Elastic Beanstalk las expone como variables de entorno.

Secretos que existen:

| Nombre | Dónde vive | Propósito |
|---|---|---|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | GitHub Secrets | Autenticar el pipeline contra AWS |
| `ECR_REPOSITORY` | GitHub Secrets | URL del registro de imágenes |
| `DATABASE_URL_DEV/STAGING/PROD` | AWS Secrets Manager | Conexión a RDS por ambiente |
| `JWT_SECRET_KEY` | AWS Secrets Manager | Firma de tokens |
| `REDIS_URL` | AWS Secrets Manager | Conexión a ElastiCache |

## 8. Escaneos de seguridad automáticos

En cada ejecución del pipeline:

- **`pip-audit`** — vulnerabilidades conocidas en dependencias Python.
- **`gitleaks`** — secretos filtrados en el código o en el historial.
- **`docker scout`** — vulnerabilidades en la imagen construida.
- **`bandit`** — patrones inseguros en el código Python (opcional).

Vulnerabilidades **críticas** bloquean el merge; las **medias** o **bajas** generan advertencias que se atienden en el siguiente sprint.

## 9. Métricas del pipeline (opcional pero recomendado)

Métricas que vale la pena observar:

- **Tiempo del pipeline**: si supera 15 minutos, se paraleliza o se optimiza.
- **Frecuencia de despliegue**: cuántos deploys a prod por semana.
- **Tasa de fallo de despliegue**: cuántos deploys revertidos.
- **Tiempo medio de recuperación (MTTR)**: cuánto se tarda en volver a estar arriba después de una caída.

Estas cuatro son las métricas **DORA** que se usan para evaluar la salud de un equipo de ingeniería.

## 10. Costo del pipeline

GitHub Actions es gratuito hasta 2.000 minutos/mes en repositorios privados con cuenta Free, y ilimitado en repositorios públicos. Para un proyecto académico eso es más que suficiente.

Los costos que sí aparecen:

- **ECR**: almacenamiento de imágenes Docker (unos pocos centavos al mes por imagen retenida).
- **Elastic Beanstalk**: no cobra por el servicio, pero sí por las EC2 y el ALB subyacentes.
- **RDS**: la instancia de DEV puede ser `db.t4g.micro` (nivel gratuito el primer año).

## 11. Local vs CI: comandos equivalentes

Antes de hacer push, se puede ejecutar el mismo pipeline localmente para atrapar errores temprano:

```bash
# Backend
make lint        # black + isort + mypy
make test-unit   # tests unitarios
make test-int    # tests de integración (con docker-compose)
make build       # docker build

# Frontend
cd frontend
npm run lint
npm run type-check
npm test
npm run build
```

El `Makefile` en la raíz del repo unifica estos comandos para evitar recordar la sintaxis exacta.

## 12. Referencias entre documentos

- La estructura de tests que el pipeline ejecuta está definida en `docs/BEST_PRACTICES.md` sección Testing.
- El proceso de desarrollo iterativo que alimenta el pipeline está en `docs/DEVELOPMENT_WORKFLOW.md`.
- El subagente responsable de mantener este pipeline es `@devops-engineer`, definido en `docs/CLAUDE_CODE_AGENTS.md`.
