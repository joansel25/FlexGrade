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

Retorna el horario armado del estudiante en el período activo.

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

Retorna el detalle de un grupo específico. Este endpoint se consulta con alta frecuencia durante la matrícula, por lo que su respuesta se cachea en Redis con TTL de 30 segundos.

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

### DELETE /enrollments/{enrollment_id}

Cancela una inscripción activa y libera el cupo. Solo el propio estudiante puede cancelar sus inscripciones.

**Response 204** (sin cuerpo)

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
