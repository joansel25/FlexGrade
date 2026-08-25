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

**Este formato es universal.** Lo usan por igual los errores de negocio, los de autenticación y los de autorización: un cliente lleva un único analizador de errores y siempre encuentra un `error.code` estable con el que decidir qué hacer. El `message` está pensado para mostrarse a una persona y puede cambiar de redacción; el `code` no cambia y es el que debe consultar el código.

Las respuestas `401` incluyen además la cabecera `WWW-Authenticate: Bearer`, como manda el estándar HTTP.

| error.code | HTTP | Cuándo |
|---|---|---|
| `MISSING_TOKEN` | 401 | La petición no trae la cabecera `Authorization` |
| `INVALID_TOKEN` | 401 | Token ilegible, con firma inválida, caducado o de tipo equivocado |
| `INVALID_CREDENTIALS` | 401 | Correo o contraseña incorrectos |
| `USER_INACTIVE` | 403 | Credenciales correctas, cuenta desactivada |
| `ADMIN_REQUIRED` | 403 | Autenticado, pero sin rol de administrador |

`MISSING_TOKEN` e `INVALID_TOKEN` se distinguen a propósito: para el cliente son situaciones distintas —una se resuelve iniciando sesión, la otra renovando el token— y sin códigos separados tendría que decidirlo interpretando el mensaje.

La única excepción a este formato son los `422`, que genera FastAPI al validar el esquema de la petición y llevan su estructura propia con la lista de campos que fallaron.

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

Se distingue de `/me/schedule` en algo más que el formato, y por eso son dos endpoints: el
horario está pensado para **leerse** —franjas sueltas ordenadas por día y hora— y este para
**operar**. Cada elemento lleva el `id` de su INSCRIPCIÓN, que es lo que exige
`DELETE /enrollments/{id}`; una franja del horario no se puede cancelar porque no tiene
identidad propia.

**Response 200**
```json
{
  "period": "2025-2",
  "period_code": "2025-2-V1",
  "items": [
    {
      "id": "uuid",
      "course_offering_id": "uuid",
      "course_id": "uuid",
      "course_code": "MAT101",
      "course_name": "Cálculo I",
      "credits": 4,
      "group_number": "01",
      "professor": "Ana Pérez",
      "schedule": [
        { "day_of_week": 1, "start_time": "08:00", "end_time": "10:00", "classroom": "A-201" }
      ],
      "enrolled_at": "2025-11-15T14:30:00Z"
    }
  ],
  "total_credits": 4
}
```

Solo llegan las **activas**: las canceladas no ocupan cupo ni aparecen en el horario, así que
mostrarlas obligaría a cada cliente a repetir el mismo filtro.

`total_credits` se suma en el servidor para que la cifra sea idéntica en la pantalla y en el
comprobante en PDF. Una lista vacía es un resultado legítimo, no un error.

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `NO_ACTIVE_PERIOD` | No hay ventana de matrícula activa |

### GET /students/me/history

Retorna el historial académico completo del estudiante.

### GET /students/me/study-plan

Retorna el plan de estudios de la carrera que cursa el estudiante.

Responde «qué materias son las mías», que `GET /courses` no puede contestar: el catálogo lista
**todas** las materias de la institución, así que un estudiante de Derecho veía Programación II,
abría su ficha, pulsaba «Inscribir» y solo entonces recibía un `403 COURSE_NOT_IN_PROGRAM`. La
regla del servidor era correcta; el problema era que la interfaz ofrecía algo que iba a fallar.

**Response 200**
```json
{
  "program_id": "uuid",
  "program_code": "ISIS",
  "program_name": "Ingeniería de Sistemas",
  "total_semesters": 10,
  "courses": [
    {
      "id": "uuid",
      "code": "MAT101",
      "name": "Cálculo I",
      "credits": 4,
      "description": "Fundamentos de cálculo diferencial",
      "suggested_semester": 1,
      "is_mandatory": true
    }
  ],
  "total_credits": 29
}
```

`suggested_semester` e `is_mandatory` **no son propiedades de la materia** sino de su relación
con el programa: Cálculo I puede ser de primer semestre y obligatoria en Ingeniería, y de tercero
y electiva en Administración. Por eso viven en `program_courses` y solo este endpoint los expone;
`GET /courses` no puede devolverlos porque no sabe de qué programa se habla.

Va **sin paginar**, al contrario que el catálogo: un plan tiene decenas de materias y su valor
está en verse entero. La pregunta que responde es «qué me falta para graduarme», y esa no se
contesta de veinte en veinte.

El programa **sale del token**, nunca de la petición. Aceptarlo como parámetro permitiría
consultar el plan de otra carrera, y con él la interfaz volvería a ofrecer materias no
inscribibles.

Un plan vacío es un resultado legítimo: significa que Registro Académico todavía no lo cargó.

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `STUDENT_PROFILE_NOT_FOUND` | La cuenta no tiene perfil académico |
| 404 | `PROGRAM_NOT_FOUND` | El programa del estudiante ya no existe |

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

Retorna el detalle de una materia y, si se indica un plan de estudios, lo que exige dentro de él.

**Query params**

| Param | Tipo | Descripción |
|---|---|---|
| `program_id` | UUID | Plan sobre el que resolver prerrequisitos y correquisitos |

`program_id` es opcional pero no accesorio: **sin él las dos listas de requisitos vuelven vacías** y `program_id` vuelve como `null`. Un requisito no une dos materias sino dos materias dentro de una carrera, así que «qué exige MAT102» no tiene una respuesta única. Devolver la unión de todos los planes sería peor que no devolver nada: no es cierta en ninguna carrera concreta, y a un estudiante de Derecho le mostraría los requisitos de Ingeniería como si fueran suyos. El frontend envía siempre el programa del estudiante, que obtiene de `GET /students/me/study-plan`.

**Response 200**
```json
{
  "id": "uuid",
  "code": "MAT102",
  "name": "Cálculo II",
  "credits": 4,
  "description": "Cálculo integral y series",
  "program_id": "uuid",
  "prerequisites": [
    {
      "id": "uuid",
      "code": "MAT101",
      "name": "Cálculo I"
    }
  ],
  "corequisites": [
    {
      "id": "uuid",
      "code": "TAL101",
      "name": "Taller de Cálculo I"
    }
  ]
}
```

`prerequisites` son las materias que hay que **haber aprobado antes**; `corequisites`, las que hay que **cursar en el mismo período**. Se devuelven en dos listas y no en una con el tipo dentro porque lo que la interfaz hace con cada una es distinto, y una lista mezclada obligaría a repartirla en cada pantalla.

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
| 409 | `PREREQUISITES_NOT_MET` | Faltan materias prerrequisito por aprobar |
| 409 | `COREQUISITES_NOT_MET` | Faltan correquisitos por inscribir en este mismo período |
| 403 | `COURSE_NOT_IN_PROGRAM` | La materia no pertenece al programa del estudiante |

**Notas de implementación**

- El **estudiante sale del token**, nunca del cuerpo. Aceptarlo del cliente permitiría inscribir a otra persona.
- El **período tampoco se puede elegir**: es siempre el activo. Dejarlo por parámetro permitiría inscribirse contra semestres ya cerrados.
- `enrolled_at` lo asigna PostgreSQL con su `DEFAULT NOW()`, no la aplicación: es la única fuente horaria fiable cuando varias instancias pueden tener relojes ligeramente distintos.
- Reinscribirse en un grupo que se canceló antes **reactiva la fila existente** en vez de crear otra. La restricción `UNIQUE (student_id, course_offering_id, enrollment_period_id)` lo impediría, y borrar la anterior perdería el rastro de que hubo una cancelación.
- El descuento del cupo y la creación de la inscripción ocurren en **una sola transacción**. Ver `DATA_MODEL.md`, «Concurrencia en el descuento de cupos», para el mecanismo que impide el sobrecupo.

Los `details` del error llevan lo que el cliente necesita para explicarlo sin interpretar el mensaje: `COURSE_CAPACITY_EXCEEDED` incluye `capacity` y `enrolled`; `PREREQUISITES_NOT_MET`, la lista `missing_prerequisites` con los códigos que faltan; `COREQUISITES_NOT_MET`, la lista `missing_corequisites`; y `SCHEDULE_CONFLICT`, el `conflicting_offering_id` con el día y la hora del cruce.

`PREREQUISITES_NOT_MET` y `COREQUISITES_NOT_MET` son códigos distintos a propósito, aunque los dos digan «te falta una materia». Lo que se puede hacer al recibirlos no es lo mismo: ante un prerrequisito que falta no hay nada que hacer hoy —hay que aprobarlo en otro semestre—, mientras que un correquisito que falta se resuelve inscribiendo la otra materia a continuación. Un solo código obligaría a la interfaz a adivinar cuál de las dos cosas decir.

**Los requisitos se evalúan en el plan de estudios del ESTUDIANTE**, no en un plan cualquiera: la misma materia puede exigir cosas distintas en dos carreras, y lo que obliga a esta persona es lo que diga su plan. Los correquisitos **mutuos** —el bloque teoría + laboratorio— no exigen estar ya inscritos; el porqué está en `DATA_MODEL.md`, sección «Requisitos académicos».

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

Todos los endpoints de esta sección exigen `Authorization: Bearer <access_token>` de una cuenta con rol `ADMIN`. La exigencia se declara una sola vez, en el router, y no endpoint por endpoint: así proteger es el comportamiento por defecto y no algo que haya que recordar al añadir uno nuevo.

- Sin token → `401 MISSING_TOKEN`
- Con token de estudiante → `403 ADMIN_REQUIRED`

### POST /admin/enrollment-periods

Crea un nuevo período de matrícula, **siempre desactivado**. Abrir la ventana es una operación aparte (`PUT .../activate`).

Separarlas permite preparar el período con semanas de antelación —revisando fechas, creando sus grupos— sin que se abra solo al llegar la fecha, y permite cerrarlo de inmediato ante un incidente sin tener que tocar el calendario.

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

**Response 201** — el período creado, con `is_active: false`.

| Código HTTP | error.code | Situación |
|---|---|---|
| 409 | `DUPLICATE_PERIOD_CODE` | Ya existe una ventana con ese código |
| 409 | `INVALID_PERIOD_RANGE` | El cierre no es posterior a la apertura |

Ambas condiciones las impondría igualmente la base de datos —la restricción `UNIQUE` y el `CHECK (ends_at > starts_at)`—, pero devolverían un error de restricción opaco. Comprobarlas antes permite responder con un mensaje que dice qué corregir.

### PUT /admin/enrollment-periods/{id}/activate

Activa un período. Solo puede haber un período activo a la vez; activar uno nuevo desactiva el anterior **en la misma transacción**, porque el índice único parcial `ix_enrollment_periods_active` rechazaría el estado intermedio con dos activos.

### POST /admin/courses

Crea una nueva materia en el catálogo.

**Request**
```json
{
  "code": "QUI101",
  "name": "Química General",
  "credits": 3,
  "description": "Fundamentos de química"
}
```

**Response 201** — la materia creada, con el código normalizado en mayúsculas.

| Código HTTP | error.code | Situación |
|---|---|---|
| 400 | `DOMAIN_ERROR` | El código no cumple el formato institucional (`MAT101`) |
| 409 | `DUPLICATE_COURSE_CODE` | Ya existe una materia con ese código |

Crear la materia no la pone en oferta: hasta que no se le abre un grupo con
`POST /admin/offerings` no aparece en `GET /courses/{id}/offerings` ni se puede inscribir.

### POST /admin/offerings

Crea un nuevo grupo para el período activo. El período **no** viaja en el cuerpo: se toma del
que esté activo. Aceptarlo permitiría abrir grupos en un semestre cerrado con un identificador
copiado de otro, y el error solo se notaría cuando los estudiantes no vieran la materia.

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

**Response 201** — el grupo creado, con la misma forma que devuelve `GET /offerings/{id}`.

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `NO_ACTIVE_PERIOD` | No hay ninguna ventana de matrícula activa |
| 404 | `COURSE_NOT_FOUND` | La materia indicada no existe |
| 404 | `PROFESSOR_NOT_FOUND` | El docente indicado no existe |
| 409 | `DUPLICATE_OFFERING_GROUP` | Ese número de grupo ya existe para la materia en el período |
| 409 | `OVERLAPPING_SCHEDULE` | Dos franjas del propio horario se cruzan entre sí |

### PUT /admin/offerings/{id}/capacity

Ajusta el cupo total de un grupo. No permite reducir por debajo del número de inscritos actuales.

**Request**
```json
{ "total_capacity": 45 }
```

**Response 200** — el grupo con su cupo ya ajustado.

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `OFFERING_NOT_FOUND` | El grupo no existe |
| 409 | `CAPACITY_BELOW_ENROLLED` | El cupo pedido es menor que los inscritos actuales |
| 409 | `CONCURRENT_MODIFICATION` | Otra operación modificó el grupo; repetir la petición |

Es la única operación de administración que **invalida la caché**: la entrada
`catalog:v1:offering:{id}` guarda `total_capacity`, y servirla caducada junto a un
`enrolled_count` fresco daría unos cupos disponibles que no cuadran.

El `UPDATE` se condiciona por `version` —bloqueo optimista— y se reintenta hasta tres veces.
Aquí ese mecanismo sí es el adecuado, al contrario que en el descuento de cupo: dos
administradores ajustando el mismo grupo a la vez es excepcional, y cuando ocurre es mejor
rechazar la segunda escritura que dejar que pise en silencio la decisión de la primera.

### GET /admin/reports/enrollments

Retorna el reporte de inscripciones del período activo. Las cifras se calculan **en vivo** en
cada llamada: no se cachean ni se precalculan, porque se consultan mientras la matrícula está
ocurriendo y una cifra de hace treinta segundos que parece actual es peor que no tener reporte.

Cuenta solo inscripciones con estado `ENROLLED` del período activo. Las canceladas y las de
períodos anteriores quedan fuera de todas las cifras.

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

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `NO_ACTIVE_PERIOD` | No hay ninguna ventana de matrícula activa |

`total_enrollments` cuenta inscripciones; `unique_students`, personas. No coinciden porque cada
estudiante matricula varias materias. `active_offerings` son los grupos con al menos una
inscripción activa, no los grupos abiertos.

### GET /admin/reports/occupancy

Retorna la ocupación por grupo (porcentaje de cupo utilizado), **de más lleno a más vacío**. El
orden no es cosmético: la primera página trae justo los grupos sobre los que hay que decidir si
se amplía el cupo o se abre otro grupo.

**Query params:** `page` (por defecto 1) y `size` (por defecto 20, máximo 100).

Va paginado aunque el resto de reportes no lo esté: los programas de la institución son decenas
y no crecen, pero los grupos de un período son cientos y aumentan cada semestre.

**Response 200**
```json
{
  "period_code": "2025-2-V1",
  "generated_at": "2025-11-15T14:30:00Z",
  "offerings": [
    {
      "offering_id": "550e8400-e29b-41d4-a716-446655440000",
      "course_code": "MAT101",
      "course_name": "Cálculo I",
      "group_number": "01",
      "total_capacity": 40,
      "enrolled_count": 37,
      "available_slots": 3,
      "occupancy_rate": 92.5
    }
  ],
  "total": 87,
  "page": 1,
  "size": 20
}
```

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `NO_ACTIVE_PERIOD` | No hay ninguna ventana de matrícula activa |

La ocupación se calcula sobre `course_offerings.enrolled_count` —el mismo contador que decide
si queda cupo— y no con un `COUNT` sobre `enrollments`: así el reporte muestra exactamente el
número contra el que se está compitiendo, sin tocar la tabla más caliente del sistema durante
el pico.

## 7. Comprobantes

### GET /students/me/receipt

Genera y descarga el comprobante de matrícula del estudiante en formato PDF.

**Response 200** con `Content-Type: application/pdf`, `Content-Disposition: attachment` y un
nombre de archivo que incluye el código del estudiante y el período
(`comprobante-matricula-1234567-2025-2-V1.pdf`), para que quien descargue varios a lo largo del
semestre pueda distinguirlos sin abrirlos.

Lleva `Cache-Control: no-store`: el contenido cambia con cada inscripción, y una copia guardada
por el navegador mostraría materias ya canceladas.

El documento se genera **al vuelo en cada petición** y no se almacena en ningún sitio. Durante
la ventana de matrícula el contenido cambia con cada operación, así que un archivo guardado
quedaría obsoleto de inmediato; y ponerlo en S3 obligaría a invalidarlo en cada inscripción,
para un documento que se descarga una o dos veces por semestre.

Los créditos que imprime son **los mismos** que devuelve `GET /students/me/enrollments`: el
comprobante reutiliza ese caso de uso en vez de repetir sus consultas, precisamente para que las
dos cifras no puedan discrepar.

Un comprobante **sin materias es un documento válido**, no un error: certifica que la persona no
inscribió nada en el período.

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `STUDENT_PROFILE_NOT_FOUND` | La cuenta no tiene perfil académico |
| 404 | `NO_ACTIVE_PERIOD` | No hay ventana de matrícula activa |

El comprobante incluye un **código de verificación** determinista (`{period_code}-{student_code}`)
con el que Registro Académico puede localizar la matrícula. **No es una firma electrónica** y el
propio documento lo dice: no prueba que el PDF no se haya alterado. Firmarlo exigiría un
certificado y una gestión de claves que este proyecto no contempla.

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
