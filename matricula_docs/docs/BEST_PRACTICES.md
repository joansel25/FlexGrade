# Buenas prácticas de programación

Este documento define las convenciones y prácticas que se aplican en el desarrollo del sistema. No es una lista teórica: cada regla tiene una razón concreta relacionada con la mantenibilidad, la calidad o la seguridad del código.

## 1. Estilo y convenciones de código

### Python

- **PEP 8** como base, con **line length de 100** (no 79). Formateo automático con **Black**.
- **Type hints obligatorios** en toda función pública. Se validan con `mypy` en modo estricto.
- **Nombres:** `snake_case` para funciones y variables, `PascalCase` para clases, `SCREAMING_SNAKE_CASE` para constantes.
- **Imports ordenados** con `isort`: stdlib, terceros, locales.
- **Docstrings** en formato Google en toda función pública.
- **Sin `print()`** en código de producción. Se usa `logging` estructurado.

```python
# Bien
def enroll_student(
    student_id: UUID,
    offering_id: UUID,
) -> Enrollment:
    """Inscribe a un estudiante en un grupo.

    Args:
        student_id: Identificador único del estudiante.
        offering_id: Identificador del grupo (course_offering).

    Returns:
        La inscripción creada.

    Raises:
        CapacityExceededError: Si el grupo no tiene cupos.
        AlreadyEnrolledError: Si el estudiante ya está inscrito.
    """
    ...

# Mal
def enroll(sid, oid):
    print("enrolling")
    ...
```

### TypeScript (frontend)

- **ESLint + Prettier** con configuración estricta.
- **Modo estricto de TypeScript** (`strict: true`).
- **Sin `any`.** Si algo es realmente desconocido, se usa `unknown` y se hace narrowing explícito.
- **Componentes funcionales** con hooks; sin componentes de clase.
- **Nombres:** `PascalCase` para componentes y tipos, `camelCase` para funciones y variables.
- **Estructura por feature**, no por tipo de archivo.

## 2. Nombres significativos

Los nombres se eligen para revelar intención. No hay abreviaturas caprichosas ni prefijos innecesarios.

| ✗ Mal | ✓ Bien | Por qué |
|---|---|---|
| `def get(id)` | `def find_enrollment_by_id(enrollment_id)` | Dice qué recupera y sobre qué |
| `data = get_stuff()` | `active_enrollments = enrollment_repo.find_active_by_student(...)` | Nombre = contenido |
| `class Manager` | `class EnrollmentValidator` | Nombre = responsabilidad concreta |
| `def process(x)` | `def reserve_slot()` | Verbo específico del dominio |
| `flag = True` | `is_period_active = True` | Booleanos leen como pregunta |

## 3. Funciones pequeñas y con propósito único

- **Máximo 20-30 líneas** por función. Si crece más, casi siempre hay dos responsabilidades mezcladas.
- **Un único nivel de abstracción** por función. No mezclar orquestación con detalles de bajo nivel.
- **Máximo 3-4 parámetros.** Si necesitas más, agrupa en un objeto (DTO o value object).
- **Retornos tempranos** para reducir anidamiento.

```python
# Bien
def enroll_student(student_id: UUID, offering_id: UUID) -> Enrollment:
    period = _get_active_period()
    student = _load_student(student_id)
    offering = _load_offering(offering_id)

    _validate_can_enroll(student, offering, period)
    return _perform_enrollment(student, offering, period)

# Mal: 80 líneas mezclando validación, persistencia y notificación
def enroll_student(student_id, offering_id):
    # ... 80 líneas con todo mezclado
```

## 4. Manejo de errores

### Excepciones específicas del dominio

Nunca se lanzan excepciones genéricas. Cada error del dominio tiene su clase:

```python
class DomainError(Exception):
    """Base para todas las excepciones del dominio."""

class CapacityExceededError(DomainError): ...
class PrerequisitesNotMetError(DomainError): ...
class ScheduleConflictError(DomainError): ...
class AlreadyEnrolledError(DomainError): ...
```

### Traducción en la capa de API

Un handler centralizado convierte excepciones de dominio en códigos HTTP:

```python
@app.exception_handler(CapacityExceededError)
async def capacity_handler(request, exc):
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "COURSE_CAPACITY_EXCEEDED", "message": str(exc)}}
    )
```

### Fail fast

Validar en el borde más externo posible. Si un input es inválido, se rechaza antes de tocar la base de datos, no después.

### No silenciar excepciones

Un `except Exception: pass` está prohibido salvo justificación explícita en un comentario que explique por qué.

## 5. Comentarios y documentación

### El código se explica solo; los comentarios explican *por qué*

```python
# Mal (redundante)
# Incrementa el contador
counter += 1

# Bien (explica el por qué)
# El offset se ajusta a UTC porque algunos clientes reportan hora local
timestamp = timestamp.astimezone(timezone.utc)
```

### Docstrings donde importan

- Toda función pública.
- Toda clase que forme parte de la API interna del módulo.
- Los archivos `__init__.py` explican brevemente qué contiene el módulo.

### `TODO`, `FIXME` y `HACK`

Se usan con el nombre del autor y una fecha o ticket:

```python
# TODO(sebas, 2025-11-20): reemplazar por cache distribuido
# FIXME(sebas, PROJ-123): mal manejo de zona horaria
```

## 6. Testing

### Tres niveles claros

- **Unit tests**: dominio y casos de uso con dobles de test (mocks / in-memory). Corren en milisegundos. Son la mayoría.
- **Integration tests**: adaptadores contra infraestructura real (Testcontainers levanta PostgreSQL y Redis).
- **E2E tests**: API completa contra la aplicación levantada.

### Cobertura como consecuencia, no como meta

No se persigue un porcentaje específico. Lo que se persigue es **que todo camino crítico esté probado**. En este proyecto, los caminos críticos son:

1. La operación de inscripción (concurrencia, validaciones, transacción).
2. La validación de prerrequisitos.
3. La detección de conflictos de horario.
4. La autenticación y autorización.

### Naming de tests

Nombres largos y descriptivos con formato `test_<qué>_<cuándo>_<resultado_esperado>`:

```python
def test_enroll_student_when_offering_is_full_raises_capacity_exceeded():
    ...

def test_enroll_student_when_prerequisites_not_met_raises_prerequisites_error():
    ...
```

### Un aserto por test (idealmente)

Cada test verifica una sola cosa. Si un test verifica cinco cosas y una falla, no sabes por qué.

### Fixtures y factories

Se usan factories (con `factory_boy`) para construir entidades de prueba. Evita duplicación y mantiene los tests legibles.

## 7. Control de versiones (Git)

### Ramas

- `main` — código productivo, protegido, solo merge por PR con revisión.
- `develop` — integración, opcional según flujo.
- `feature/xxx` — features en desarrollo.
- `fix/xxx` — bugs.
- `chore/xxx` — mantenimiento (dependencias, config).

### Commits: convención Conventional Commits

Formato: `<tipo>(<scope>): <descripción>`

Tipos: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`.

```
feat(enrollment): agregar validación de prerrequisitos
fix(enrollment): corregir race condition en descuento de cupo
docs(api): documentar rate limits
refactor(auth): extraer servicio JWT a puerto e interfaz
test(enrollment): agregar tests de concurrencia
```

### Commits atómicos

Un commit resuelve una cosa. Un commit gigante con "cambios varios" es difícil de revisar y de revertir.

### Pull Requests

El desarrollo diario ocurre directamente sobre `develop` y no abre PR (ver `CI_CD.md` sección 3). Los PR quedan reservados para los dos merges que promocionan código entre ambientes:

- **`develop` → `qa`**, cuando una fase está completa y lista para validarse a mano.
- **`qa` → `main`**, cuando QA aprueba y el release va a producción.
- **`hotfix` → `main`** y **`hotfix` → `develop`**, en una emergencia. Las dos, siempre: llevarlo solo a `main` haría que la siguiente entrega reintrodujera el fallo.

Cuando se abre uno:

- Descripción clara del **qué** y del **por qué**, no solo del cómo.
- Tests en verde en CI antes del merge. Sin excepciones.
- Auto-revisión hecha (`@code-reviewer`) antes de mergear.
- Merge de promoción **sin squash**: aplasta la historia de una fase entera en un commit y se pierde la trazabilidad de por qué se tomó cada decisión.

## 8. Seguridad

### Autenticación y autorización

- **Tokens JWT** con expiración corta (1 hora) y refresh token separado (7 días).
- **Contraseñas** hasheadas con `bcrypt` con cost factor 12.
- **HTTPS obligatorio** en producción. Rechazar tráfico HTTP.
- **Autorización basada en roles** verificada en cada endpoint sensible.

### Validación de entrada

- **Schemas Pydantic** validan todos los inputs de la API.
- **Nunca se confía en el cliente.** Toda validación se repite en el backend aunque el frontend ya la haya hecho.
- **SQL injection** se previene usando siempre parámetros de SQLAlchemy, jamás string interpolation.

### Manejo de secretos

- **Nunca se comitean credenciales**, tokens ni llaves. `.gitignore` cubre `.env`, `*.key`, `*.pem`.
- **Variables de entorno** para toda configuración sensible (12-factor).
- **Azure Key Vault** en producción para credenciales de DB, Redis, etc.

### Logs

- **Nunca loguear** contraseñas, tokens, PII (datos personales) sin necesidad.
- **Loguear con niveles** apropiados: DEBUG, INFO, WARNING, ERROR, CRITICAL.
- **Trazas correladas**: cada request tiene un `request_id` que aparece en todos los logs de esa operación.

### Rate limiting

Implementado a nivel de API para prevenir abuso. Los límites están documentados en `API.md`.

## 9. Rendimiento

### Reglas generales

- **Medir antes de optimizar.** Ninguna optimización sin datos que la justifiquen.
- **Consultas N+1** son bug, no detalle. Se detectan y corrigen con `eager loading` de SQLAlchemy.
- **Índices en columnas de búsqueda frecuente.** Definidos en las migraciones, no como parche posterior.

### Convenciones de base de datos

`DATA_MODEL.md` es la fuente de verdad del esquema; lo que sigue es el criterio que se aplica al crear o modificar una tabla. Las cuatro reglas nacen de defectos reales detectados en el esquema durante la Fase 1.

#### Nunca un índice manual sobre una columna que ya tiene `UNIQUE` (ni sobre la PK)

PostgreSQL crea automáticamente un índice B-tree para poder imponer la restricción `UNIQUE`, y lo mismo hace con la `PRIMARY KEY`. Un segundo índice sobre la misma columna no aporta nada en lectura: cuesta espacio en disco y, sobre todo, penaliza cada `INSERT` y cada `UPDATE`, porque hay que mantener dos estructuras en vez de una.

```sql
-- ✗ MAL — el UNIQUE de user_id ya generó un índice; este es un duplicado exacto
CREATE TABLE students (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    student_code VARCHAR(20) NOT NULL UNIQUE,
    program_id UUID NOT NULL REFERENCES programs(id)
);
CREATE INDEX ix_students_user ON students(user_id);          -- ✗ redundante
CREATE INDEX ix_students_code ON students(student_code);     -- ✗ redundante

-- ✓ BIEN — se confía en el índice del UNIQUE y se indexa solo lo que falta
CREATE INDEX ix_students_program ON students(program_id);
```

#### Siempre indexar el lado hijo de una FK que se use en joins

PostgreSQL indexa la columna **referenciada** (el lado padre, que es la PK), pero **no** la columna que referencia. Sin ese índice, cualquier join por la FK y cualquier `ON DELETE CASCADE` obligan a un sequential scan de la tabla hija. En `enrollments`, que llega a decenas de miles de filas por período, eso es la diferencia entre una consulta de milisegundos y una que se degrada con el volumen.

Ejemplo del proyecto: `students.program_id` referencia a `programs(id)`; el índice `ix_students_program` existe precisamente para eso.

#### Prefijo `ix_` para todos los índices

Es lo que genera la `naming_convention` del `MetaData` de SQLAlchemy y, por lo tanto, lo que produce `alembic revision --autogenerate`. Mezclar prefijos (`idx_` a mano, `ix_` generado) hace que dos índices equivalentes se vean distintos sin ninguna razón, y complica referenciarlos por nombre en migraciones futuras (`op.drop_index`).

| Objeto | Prefijo | Ejemplo |
|---|---|---|
| Primary key | `pk_` | `pk_students` |
| Unique | `uq_` | `uq_students_student_code` |
| Foreign key | `fk_` | `fk_students_program_id_programs` |
| Check | `ck_` | `ck_offerings_capacity` |
| Índice | `ix_` | `ix_students_program` |

#### `created_at` y `updated_at` en toda tabla transaccional, con trigger para `updated_at`

Un `DEFAULT NOW()` solo cubre la inserción. Sin trigger, la columna miente a partir del primer `UPDATE`: sigue mostrando la fecha de creación, y cualquier auditoría o sincronización incremental que dependa de ella queda inservible.

Se usa una función compartida `set_updated_at()` y un trigger `BEFORE UPDATE` por tabla. Se prefiere el trigger a `onupdate=func.now()` de SQLAlchemy porque el trigger cubre **toda** escritura —migraciones de Alembic, scripts de mantenimiento, un `psql` manual—, no solo las que pasan por el ORM.

Las tablas de catálogo estáticas (`programs`, `courses`) solo necesitan `created_at`: si nunca se actualizan, `updated_at` es ruido.

```sql
-- ✗ MAL — updated_at nunca cambia después del INSERT
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

-- ✓ BIEN — la función se define una vez y cada tabla declara su trigger
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

El detalle por tabla está en la sección "Auditoría temporal" de `DATA_MODEL.md`.

### Caché

- Se cachea lo que se lee mucho y cambia poco: catálogo de materias, listado de grupos.
- **No** se cachea el estado transaccional (cupos actuales durante la inscripción).
- **Invalidación explícita**: al ejecutar una inscripción, se invalida el caché del offering afectado.

### Paginación

Todo listado con potencial de crecimiento se pagina. Nunca se retorna una lista completa sin límite.

## 10. Configuración

### 12-factor

- **Configuración por entorno**, no hardcodeada.
- **Variables de entorno** para todo lo que cambia entre entornos.
- **Un solo binario / imagen** que se ejecuta idéntica en dev, staging y prod.

```python
# app/infrastructure/config/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_expiration_seconds: int = 3600
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
```

## 11. Dependencias

### Elegir con criterio

Cada dependencia agrega superficie de mantenimiento, riesgos de seguridad y peso. Se agrega solo si:

1. El problema no es trivial de resolver con la stdlib.
2. La librería tiene mantenimiento activo.
3. Su licencia es compatible.

### Fijar versiones

`pyproject.toml` fija versiones exactas (`==`) para reproducibilidad. Se actualiza con criterio, no automáticamente.

### Revisar periódicamente

`pip-audit` y `dependabot` para detectar vulnerabilidades conocidas.

## 12. Antipatrones que se evitan explícitamente

- **God class**: una clase que hace demasiado. Señal de que hay que dividirla.
- **Anemic domain model**: entidades sin comportamiento, solo con getters/setters. La lógica termina esparcida en servicios.
- **Primitive obsession**: usar `str` para todo (student_code, email, program_code). Se usan value objects.
- **Feature envy**: un método que toca más atributos de otro objeto que del suyo propio. Probablemente debería estar en el otro objeto.
- **Shotgun surgery**: un cambio pequeño obliga a tocar 15 archivos. Señal de mal diseño.
- **Overengineering**: agregar abstracciones que no se necesitan hoy porque "quizás algún día". YAGNI.

## 13. Revisión de código

Toda contribución pasa por revisión antes de mergear. La revisión verifica:

- ¿El código hace lo que dice que hace?
- ¿Los nombres son claros?
- ¿Está probado?
- ¿Sigue las convenciones de este documento?
- ¿Introduce deuda técnica? Si sí, ¿está documentada?
- ¿Rompe algo existente?

Las revisiones son constructivas. Los comentarios se enfocan en el código, no en el autor.

---

## Checklist rápido antes de cada commit

- [ ] El código compila y pasa los tests locales.
- [ ] `black`, `isort` y `mypy` no reportan errores.
- [ ] No hay `print()`, `console.log()` ni `TODO` sin autor y fecha.
- [ ] No hay secretos ni credenciales en el diff.
- [ ] Los nombres son claros y en español o inglés consistente con el resto.
- [ ] El commit sigue la convención `<tipo>(<scope>): <descripción>`.
