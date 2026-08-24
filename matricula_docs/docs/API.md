# API REST

Este documento describe los endpoints del Sistema de Matrícula Académica. La API sigue las convenciones REST, usa JSON en todas las respuestas y responde con códigos HTTP estándar.

## Convenciones generales

- **Base URL en desarrollo:** `http://localhost:8000/api/v1`
- **Autenticación:** Bearer token JWT en el header `Authorization: Bearer <token>`
- **Formato de fecha/hora:** ISO 8601 en UTC (`2025-11-15T14:30:00Z`)
- **Paginación:** `?page=1&size=20` — respuestas paginadas retornan `items`, `total`, `page`, `size`
- **Filtros:** query params estándar (`?program_id=X&semester=2`)

### Códigos HTTP usados

| Código | Significado |
|---|---|
| 200 | OK — operación exitosa |
| 201 | Created — recurso creado |
| 204 | No Content — operación exitosa sin cuerpo (ej. DELETE) |
| 400 | Bad Request — datos inválidos |
| 401 | Unauthorized — sin autenticación válida |
| 403 | Forbidden — autenticado pero sin permiso |
| 404 | Not Found — recurso no existe |
| 409 | Conflict — conflicto de estado (ej. cupo agotado, ya inscrito) |
| 422 | Unprocessable Entity — validación de schema falló |
| 429 | Too Many Requests — rate limit excedido |
| 500 | Internal Server Error |

### Formato estándar de errores

```json
{
  "error": {
    "code": "COURSE_CAPACITY_EXCEEDED",
    "message": "El grupo no tiene cupos disponibles",
    "details": {
      "offering_id": "550e8400-e29b-41d4-a716-446655440000",
      "capacity": 40,
      "enrolled": 40
    }
  }
}
```

## 1. Autenticación

### POST /auth/login

Autentica un usuario y retorna tokens de acceso y refresh.

**Request**
```json
{
  "email": "estudiante@tdea.edu.co",
  "password": "SecurePass123"
}
```

**Response 200**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "uuid",
    "email": "estudiante@tdea.edu.co",
    "role": "STUDENT"
  }
}
```

### POST /auth/refresh

Renueva el par de tokens usando un refresh token válido.

**Request**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response 200** — mismo cuerpo que el login pero sin el bloque `user`:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

La cuenta se vuelve a leer de la base de datos en cada refresco: si fue desactivada o cambió de rol después del login, el token nuevo lo refleja. Un access token presentado aquí se rechaza con `401 INVALID_TOKEN`; solo sirve un token de tipo `refresh`.

### POST /auth/logout

Cierra la sesión del usuario autenticado. Requiere `Authorization: Bearer <access_token>` y responde `204 No Content`.

**Alcance real (Fase 1).** Los JWT son autocontenidos y sin estado: el servidor no puede invalidar un token ya emitido sin llevar registro de los revocados. Hoy el endpoint solo verifica que el token sea válido; la invalidación efectiva es que el cliente descarte ambos tokens. Como el access token dura una hora, la ventana de exposición es acotada.

La revocación real (lista de denegación del `jti` en Redis, consultada por `get_current_user`) se implementará junto con el adaptador de Redis en la Fase 2.

## 2. Perfil del estudiante

### GET /students/me

Retorna el perfil del estudiante autenticado.

**Response 200**
```json
{
  "id": "uuid",
  "student_code": "1234567",
  "full_name": "Joan Sebastián Cárdenas",
  "email": "sebas@tdea.edu.co",
  "program": {
    "id": "uuid",
    "code": "ISIS",
    "name": "Ingeniería de Sistemas"
  },
  "current_semester": 6,
  "enrollment_date": "2022-01-15"
}
```

El identificador del estudiante sale siempre del token, nunca de la petición: no existe forma de consultar el perfil de otra cuenta por este endpoint.

### GET /students/me/schedule

Retorna el horario armado del estudiante en el período activo. Requiere `Authorization: Bearer <access_token>`; el estudiante sale del token, así que nadie puede consultar el horario de otro.

Las franjas llegan **ordenadas por día y hora**, que es como se lee un horario: el repositorio ya devuelve ordenadas las de cada grupo, pero aquí se mezclan las de varias materias.

Un estudiante sin nada inscrito recibe `200` con `blocks` vacío —es un resultado legítimo, no un error—. Si no hay período activo, responde `404 NO_ACTIVE_PERIOD`: sin semestre no hay horario al que referirse. Las inscripciones canceladas no aparecen.

**Response 200**
```json
{
  "period": "2025-2",
  "blocks": [
    {
      "course_code": "MAT101",
      "course_name": "Cálculo I",
      "group_number": "01",
      "professor": "Ana Pérez",
      "day_of_week": 1,
      "start_time": "08:00",
      "end_time": "10:00",
      "classroom": "A-201"
    }
  ]
}
```

### GET /students/me/enrollments

Retorna las inscripciones activas del estudiante en el período actual.

### GET /students/me/history

Retorna el historial académico completo del estudiante.

## 3. Catálogo académico

### GET /courses

Lista materias del catálogo con filtros opcionales.

**Query params**
- `program_id` (uuid, opcional) — filtra por programa
- `semester` (int, opcional) — filtra por semestre sugerido
- `search` (string, opcional) — búsqueda por nombre o código
- `page`, `size` — paginación

**Response 200**
```json
{
  "items": [
    {
      "id": "uuid",
      "code": "MAT101",
      "name": "Cálculo I",
      "credits": 4,
      "description": "Fundamentos de cálculo diferencial"
    }
  ],
  "total": 87,
  "page": 1,
  "size": 20
}
```

### GET /courses/{course_id}

Retorna el detalle de una materia incluyendo sus prerrequisitos.

**Response 200**
```json
{
  "id": "uuid",
  "code": "MAT102",
  "name": "Cálculo II",
  "credits": 4,
  "description": "Cálculo integral y series",
  "prerequisites": [
    {
      "id": "uuid",
      "code": "MAT101",
      "name": "Cálculo I"
    }
  ]
}
```

### GET /courses/{course_id}/offerings

Retorna los grupos disponibles de una materia en el período activo.

**Response 200**
```json
{
  "course_id": "uuid",
  "course_code": "MAT101",
  "period_code": "2025-2-V1",
  "offerings": [
    {
      "id": "uuid",
      "group_number": "01",
      "professor": "Ana Pérez",
      "total_capacity": 40,
      "enrolled_count": 37,
      "available_slots": 3,
      "schedule": [
        {
          "day_of_week": 1,
          "start_time": "08:00",
          "end_time": "10:00",
          "classroom": "A-201"
        },
        {
          "day_of_week": 3,
          "start_time": "08:00",
          "end_time": "10:00",
          "classroom": "A-201"
        }
      ]
    }
  ]
}
```

### GET /offerings/{offering_id}

Retorna el detalle de un grupo específico. Es el endpoint más consultado durante la ventana de matrícula.

**Qué se cachea y qué no.** La respuesta se sirve en dos mitades, y la distinción es deliberada:

- **La parte estática** —materia, docente, horario, `total_capacity`— se cachea en Redis con TTL de 30 segundos. Cambia como mucho una vez por semestre.
- **`enrolled_count` y, por tanto, `available_slots`** se leen **siempre** de PostgreSQL, con una consulta de una sola columna, incluso cuando el resto del grupo viene de la caché.

Sin esa separación las dos reglas del proyecto se contradirían: este documento pide cachear el endpoint y `DATA_MODEL.md` prohíbe cachear la disponibilidad de cupos. Ambas se cumplen a la vez porque solo lo volátil se relee. Servir un `available_slots` de hace treinta segundos mostraría plazas libres en un grupo lleno y llevaría al estudiante a un `409` después de creer que tenía cupo, que es exactamente el fallo que el sistema existe para impedir.

**Si Redis no está disponible**, el endpoint responde igual, leyendo todo de PostgreSQL. La caché es una optimización, nunca una fuente de verdad, y su caída degrada el rendimiento sin afectar a la corrección.

## 4. Inscripciones (operaciones críticas)

### POST /enrollments

Inscribe al estudiante autenticado en un grupo. Es la operación más sensible del sistema: se ejecuta en una transacción con bloqueo optimista para evitar sobrecupo.

**Request**
```json
{
  "course_offering_id": "uuid"
}
```

**Response 201**
```json
{
  "id": "uuid",
  "student_id": "uuid",
  "course_offering_id": "uuid",
  "course_code": "MAT101",
  "course_name": "Cálculo I",
  "group_number": "01",
  "enrolled_at": "2025-11-15T14:30:00Z",
  "status": "ENROLLED"
}
```

**Errores específicos**

| Código HTTP | error.code | Situación |
|---|---|---|
| 409 | `ENROLLMENT_PERIOD_INACTIVE` | No hay período activo o está cerrado |
| 409 | `COURSE_CAPACITY_EXCEEDED` | El grupo llegó a su cupo máximo |
| 409 | `ALREADY_ENROLLED` | El estudiante ya está inscrito en este grupo |
| 409 | `SCHEDULE_CONFLICT` | Choca con otra inscripción activa |
| 409 | `PREREQUISITES_NOT_MET` | Faltan materias prerrequisito |
| 403 | `COURSE_NOT_IN_PROGRAM` | La materia no pertenece al programa del estudiante |

**Notas de implementación**

- El **estudiante sale del token**, nunca del cuerpo. Aceptarlo del cliente permitiría inscribir a otra persona.
- El **período tampoco se puede elegir**: es siempre el activo. Dejarlo por parámetro permitiría inscribirse contra semestres ya cerrados.
- `enrolled_at` lo asigna PostgreSQL con su `DEFAULT NOW()`, no la aplicación: es la única fuente horaria fiable cuando varias instancias pueden tener relojes ligeramente distintos.
- Reinscribirse en un grupo que se canceló antes **reactiva la fila existente** en vez de crear otra. La restricción `UNIQUE (student_id, course_offering_id, enrollment_period_id)` lo impediría, y borrar la anterior perdería el rastro de que hubo una cancelación.
- El descuento del cupo y la creación de la inscripción ocurren en **una sola transacción**. Ver `DATA_MODEL.md`, «Concurrencia en el descuento de cupos», para el mecanismo que impide el sobrecupo.

Los `details` del error llevan lo que el cliente necesita para explicarlo sin interpretar el mensaje: `COURSE_CAPACITY_EXCEEDED` incluye `capacity` y `enrolled`; `PREREQUISITES_NOT_MET`, la lista `missing_prerequisites` con los códigos que faltan; y `SCHEDULE_CONFLICT`, el `conflicting_offering_id` con el día y la hora del cruce.

### DELETE /enrollments/{enrollment_id}

Cancela una inscripción activa y libera el cupo. Solo el propio estudiante puede cancelar sus inscripciones.

**Response 204** (sin cuerpo)

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `ENROLLMENT_NOT_FOUND` | La inscripción no existe **o pertenece a otra persona** |
| 409 | `ENROLLMENT_ALREADY_CANCELLED` | Ya estaba cancelada |

Cancelar una inscripción ajena responde `404`, exactamente igual que si no existiera. Es deliberado: un `403` confirmaría que ese identificador corresponde a una inscripción real y permitiría enumerarlas probando identificadores.

Cancelar dos veces se rechaza porque liberaría el cupo dos veces, dejando `enrolled_count` por debajo de la ocupación real. Ese hueco fantasma lo podrían tomar dos personas.

## 5. Períodos de matrícula

### GET /enrollment-periods/current

Retorna el período de matrícula activo, si existe.

**Response 200**
```json
{
  "id": "uuid",
  "code": "2025-2-V1",
  "name": "Matrícula 2025-2 primera vuelta",
  "starts_at": "2025-11-15T08:00:00Z",
  "ends_at": "2025-11-17T18:00:00Z",
  "is_active": true,
  "time_remaining_seconds": 172800
}
```

**Response 404** cuando no hay período activo.

### GET /enrollment-periods

Lista todos los períodos de matrícula (paginado).

## 6. Administración (requiere rol ADMIN)

### POST /admin/enrollment-periods

Crea un nuevo período de matrícula.

**Request**
```json
{
  "code": "2026-1-V1",
  "academic_period": "2026-1",
  "name": "Matrícula 2026-1 primera vuelta",
  "starts_at": "2026-01-20T08:00:00Z",
  "ends_at": "2026-01-22T18:00:00Z"
}
```

### PUT /admin/enrollment-periods/{id}/activate

Activa un período. Solo puede haber un período activo a la vez; activar uno nuevo desactiva el anterior.

### POST /admin/courses

Crea una nueva materia en el catálogo.

### POST /admin/offerings

Crea un nuevo grupo para el período activo.

**Request**
```json
{
  "course_id": "uuid",
  "professor_id": "uuid",
  "group_number": "02",
  "total_capacity": 40,
  "schedule": [
    {
      "day_of_week": 2,
      "start_time": "10:00",
      "end_time": "12:00",
      "classroom": "B-101"
    }
  ]
}
```

### PUT /admin/offerings/{id}/capacity

Ajusta el cupo total de un grupo. No permite reducir por debajo del número de inscritos actuales.

### GET /admin/reports/enrollments

Retorna el reporte de inscripciones del período activo.

**Response 200**
```json
{
  "period_code": "2025-2-V1",
  "generated_at": "2025-11-15T14:30:00Z",
  "totals": {
    "total_enrollments": 4832,
    "unique_students": 1245,
    "active_offerings": 87
  },
  "by_program": [
    {
      "program_code": "ISIS",
      "program_name": "Ingeniería de Sistemas",
      "enrollments": 1520,
      "students": 380
    }
  ]
}
```

### GET /admin/reports/occupancy

Retorna la ocupación por grupo (porcentaje de cupo utilizado).

## 7. Comprobantes

### GET /students/me/receipt

Genera y descarga el comprobante de matrícula del estudiante en formato PDF.

**Response 200** con `Content-Type: application/pdf`.

## Consideraciones técnicas

### Rate limiting

Los endpoints están protegidos con rate limiting distinto por tipo:

| Endpoint | Límite |
|---|---|
| POST /auth/login | 5 requests / minuto por IP |
| POST /enrollments | 30 requests / minuto por usuario |
| GET /courses, /offerings | 120 requests / minuto por usuario |
| Endpoints de admin | 60 requests / minuto por usuario |

### Idempotencia

`POST /enrollments` acepta el header `Idempotency-Key: <uuid>` opcional. Si se recibe el mismo key dos veces en menos de 5 minutos, la segunda llamada retorna el mismo resultado que la primera sin ejecutar la operación de nuevo. Esto protege contra reintentos accidentales del frontend.

### Caché HTTP

- Endpoints de catálogo (`GET /courses`, `GET /offerings`) responden con `Cache-Control: public, max-age=30`.
- Endpoints de estudiante (`GET /students/me/*`) responden con `Cache-Control: private, no-cache`.

### Versionado

La API se versiona en la URL (`/api/v1/`). Cambios incompatibles se publican en `/api/v2/` manteniendo v1 en paralelo por al menos un semestre.

### Documentación interactiva

FastAPI expone automáticamente:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

## Endpoints ausentes intencionalmente

Algunas funcionalidades quedan explícitamente fuera del alcance del núcleo:

- **Chat / notificaciones en tiempo real** — se implementa como mejora futura con WebSockets.
- **Integración con pagos** — el sistema es de gestión académica, no de cartera.
- **Reportes exportables a Excel** — el frontend puede generar CSV desde los endpoints existentes.
- **Autoservicio de reset de contraseña** — se maneja por el flujo de Cognito.

Estas ausencias siguen el principio YAGNI (You Aren't Gonna Need It): no se implementa lo que no está en los requisitos.
