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
      "enrolled_at": "2025-11-15T14:30:00Z",
      "pending_corequisites": []
    }
  ],
  "total_credits": 4
}
```

Solo llegan las **activas**: las canceladas no ocupan cupo ni aparecen en el horario, así que
mostrarlas obligaría a cada cliente a repetir el mismo filtro.

`pending_corequisites` lleva los códigos que esa materia exige cursar **al mismo tiempo** y que
todavía no están inscritos ni aprobados. Casi siempre va vacío, porque la inscripción no acepta
que falte un correquisito. La excepción es el bloque de correquisitos **mutuos**: se permite
inscribirlo de una en una —si no, ninguna de las dos podría entrar nunca—, así que existe un
instante con media pareja inscrita. Ese estado es legítimo y transitorio, pero esconderlo lo
vuelve permanente: nadie completa lo que no sabe que le falta. Se calcula en el servidor porque
es la misma regla que decide si la inscripción se acepta, y duplicarla en el cliente garantiza
que un día discrepen.

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

Desde la iteración 6.3 cada materia llega además con **el punto en que está el estudiante**, y
por eso el mismo plan responde distinto para dos personas de la misma carrera:

| `status` | Significado | Qué ofrece la pantalla |
|---|---|---|
| `APPROVED` | Ya la aprobó | Nada; no hay acción |
| `ENROLLED` | La cursa en el período vigente | Ir a «Mis materias» |
| `AVAILABLE` | Puede inscribirla ahora | Entrar a la ficha y elegir grupo |
| `NOT_OFFERED` | Cumple requisitos, pero no hay grupos | Nada; entrar llevaría a una lista vacía |
| `BLOCKED` | Le falta algo | Nada, pero se dice QUÉ le falta |

Con `BLOCKED` llegan `missing_prerequisites` —lo que hay que aprobar antes— y
`missing_corequisites` —lo que habría que cursar a la vez y este período no tiene grupos—.
`corequisites` llega **siempre** que existan, también en `AVAILABLE`: es una instrucción y no
un impedimento, y esconderla hasta que la inscripción falle sería repetir el error que arregló
la 6.1.

**El cálculo va en el servidor, y no es una preferencia.** `StudyPlanStatusResolver` delega en
`PrerequisiteValidator` y `CorequisiteValidator`, los mismos objetos que deciden si
`POST /enrollments` acepta o rechaza. Una segunda versión de la regla en el navegador
funcionaría el primer día y discreparía el día que una de las dos cambiara, y entonces la
pantalla ofrecería lo que el servidor rechaza sin que nadie pudiera saber cuál de las dos
miente.

**Funciona fuera de la ventana de matrícula.** «Qué me falta para graduarme» se pregunta todo el
año, así que no haya período activo no es un error: significa que nada se ofrece, y lo que
cumple requisitos sale como `NOT_OFFERED` en vez de como disponible.

**Response 200**
```json
{
  "program_id": "uuid",
  "program_code": "ISIS",
  "program_name": "Ingeniería de Sistemas",
  "total_semesters": 10,
  "approved_credits": 4,
  "courses": [
    {
      "id": "uuid",
      "code": "MAT101",
      "name": "Cálculo I",
      "credits": 4,
      "description": "Fundamentos de cálculo diferencial",
      "suggested_semester": 1,
      "is_mandatory": true,
      "status": "APPROVED",
      "missing_prerequisites": [],
      "missing_corequisites": [],
      "corequisites": []
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

**Response 200**
```json
{
  "cancelled": [
    {
      "id": "uuid",
      "course_offering_id": "uuid",
      "course_code": "FIS101",
      "course_name": "Física I",
      "group_number": "01"
    },
    {
      "id": "uuid",
      "course_offering_id": "uuid",
      "course_code": "FIS102",
      "course_name": "Laboratorio de Física I",
      "group_number": "01"
    }
  ]
}
```

**Devuelve una lista, y respondía `204 No Content` hasta la iteración 6.2.1.** El cambio no es
cosmético: cancelar puede arrastrar más de una inscripción, y con un `204` desaparecerían dos
materias de la pantalla tras pulsar «Cancelar» en una sola, sin nada que lo explicara. Eso se
lee como una avería, no como la regla que es.

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `ENROLLMENT_NOT_FOUND` | La inscripción no existe **o pertenece a otra persona** |
| 409 | `ENROLLMENT_ALREADY_CANCELLED` | Ya estaba cancelada |
| 409 | `COREQUISITE_DEPENDENCY` | Otra materia inscrita exige cursar esta al mismo tiempo |

Cancelar una inscripción ajena responde `404`, exactamente igual que si no existiera. Es deliberado: un `403` confirmaría que ese identificador corresponde a una inscripción real y permitiría enumerarlas probando identificadores.

Cancelar dos veces se rechaza porque liberaría el cupo dos veces, dejando `enrolled_count` por debajo de la ocupación real. Ese hueco fantasma lo podrían tomar dos personas.

**Cancelar también respeta los correquisitos.** No es evidente —inscribir y cancelar parecen
operaciones independientes—, pero sin esa comprobación cancelar sería una puerta trasera al
estado que la inscripción rechaza: quien inscribe `FIS101` junto a `MAT101`, como exige la
regla, podría cancelar `MAT101` un segundo después y seguir cursando Física sin el Cálculo que
la acompaña. La decisión se reparte según la dirección del requisito:

- **Dependencia en un solo sentido.** Se rechaza con `COREQUISITE_DEPENDENCY` mientras la
  materia que depende siga inscrita. Los `details` traen `required_by` con sus códigos, porque
  la salida es concreta: cancelar antes esas. El orden correcto existe y la persona puede
  seguirlo.
- **Dependencia mutua.** Se cancela el **bloque entero**, y por eso la respuesta es una lista.
  Rechazarla dejaría las dos materias imposibles de abandonar para siempre, que es el bloqueo
  circular de la inscripción con el signo cambiado. Si el bloque se cursa como una unidad, se
  abandona como una unidad.

### Espacios en el horario de un grupo

Al abrir un grupo, cada franja indica el aula por su **código** (`space_code`), no por un identificador:

```json
{ "day_of_week": 1, "start_time": "08:00", "end_time": "10:00", "space_code": "A-201" }
```

El código es la clave natural del espacio: es lo que aparece en un horario impreso y lo que una persona escribe, así que exigir un UUID que nadie tiene a mano solo añadiría un paso. La comparación **no distingue mayúsculas ni espacios sobrantes** —`  a-201 ` encuentra `A-201`—, porque obligar a acertar el formato exacto convertiría un dato correcto en un 404. Un código ausente del inventario responde `404 SPACE_NOT_FOUND` con ese mismo código en `details`, y el grupo no se crea. `space_code` es opcional: una franja sin aula es normal, porque el horario se publica antes de repartir espacios.

**Lo que se DEVUELVE no cambió.** Las respuestas con horario —catálogo, «Mis materias», horario y comprobante— siguen exponiendo `classroom` con el código del aula. El aula pasó a ser una entidad por dentro; quien lee un horario sigue queriendo leer «A-201», así que el contrato público se mantuvo estable a propósito.

### GET /admin/spaces/available

Responde qué espacios están libres en una franja del período activo. Es lo que convierte la asignación de aulas de un ejercicio de memoria en una consulta: sin esto, la única forma de encontrar un aula libre es probar códigos contra `POST /admin/offerings` y coleccionar rechazos.

**Query params**

| Param | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `day_of_week` | 1–7 | sí | 1 = lunes … 7 = domingo |
| `start_time` | `HH:MM` | sí | Inicio de la franja que se quiere ocupar |
| `end_time` | `HH:MM` | sí | Fin de la franja; posterior al inicio |
| `min_capacity` | entero | no | Personas que tienen que caber |
| `space_type` | enum | no | `CLASSROOM`, `LABORATORY` o `AUDITORIUM` |

**Response 200**
```json
{
  "day_of_week": 2,
  "start_time": "10:00:00",
  "end_time": "12:00:00",
  "items": [
    { "id": "uuid", "code": "B-101", "name": null, "space_type": "CLASSROOM",
      "capacity": 50, "campus": "Sede Principal", "building": "B" }
  ],
  "total": 1
}
```

La respuesta repite la franja consultada. Una lista suelta no dice a qué pregunta contesta, y quien la lee más tarde —o la copia a un informe— no puede saber si era el martes de 10 a 12.

**La disponibilidad usa el MISMO criterio que el rechazo.** Un espacio está libre si ninguna franja suya se solapa con la pedida, con la misma comparación estricta de `SpaceConflictDetector` y el rango `[)` de la restricción: una clase que termina a las 10:00 deja el aula libre a las 10:00. Si los dos criterios divergieran, esta consulta ofrecería aulas que `POST /admin/offerings` rechaza, o escondería aulas que acepta.

**Un aula sin aforo registrado aparece igual aunque se pida un mínimo**, con `capacity: null`. Es la misma decisión que en toda la Fase 7: excluirla escondería un aula que probablemente sirve, y prometer que cabe sería peor. Quien consulta ve el `null` y decide.

Una franja al revés —`start_time` posterior a `end_time`— responde `400`, no una lista vacía: devolver cero aulas dejaría a quien pregunta creyendo que no hay ninguna libre.

### Errores al asignar un aula

| Código HTTP | error.code | Situación |
|---|---|---|
| 400 | `INVALID_SCHEDULE_BLOCK` | La franja está mal formada (fin anterior al inicio, día fuera de rango) |
| 404 | `SPACE_NOT_FOUND` | El código de aula no está en el inventario |
| 409 | `SPACE_DOUBLE_BOOKED` | El aula ya está ocupada a esa hora en el período |
| 409 | `SPACE_CAPACITY_EXCEEDED` | El grupo no cabe en el aula |

`SPACE_DOUBLE_BOOKED` trae en `details` el aula, el día, la hora y `occupied_by` con la materia y el grupo que la ocupan: «el aula está ocupada» deja a quien programa buscando a ciegas, y con el grupo delante sabe con quién hablar. `SPACE_CAPACITY_EXCEEDED` trae el aforo y los cupos pedidos.

Un aula **sin aforo registrado no bloquea nada**. Los espacios que nacieron del traslado de textos de la 7.1 no traen ese dato, y tratar ese «no sé» como un «no cabe» inutilizaría aulas válidas por una laguna del inventario.

Detrás de la validación hay una restricción de exclusión de PostgreSQL que rechaza el estado aunque el código falle; el reparto de papeles es el mismo que impide el sobrecupo y está explicado en `DATA_MODEL.md`, «Doble reserva de un espacio».

### POST /auth/refresh — la respuesta lleva la cuenta

Además del par de tokens, la respuesta incluye `user` con `id`, `email` y `role`, igual que el login:

```json
{ "access_token": "...", "refresh_token": "...", "token_type": "bearer",
  "expires_in": 900, "user": { "id": "uuid", "email": "…", "role": "ADMIN" } }
```

No es una comodidad. Este endpoint es el que **restaura la sesión al recargar la página**, y sin ese dato el frontend recuperaría el acceso sin saber quién entró. Con el rol perdido, las rutas protegidas por rol —las de administración— expulsarían a un administrador legítimo en cuanto refrescara la pestaña. El caso de uso ya carga el usuario para comprobar que la cuenta sigue activa, así que devolverlo no cuesta ninguna consulta más.

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

### POST /admin/spaces

Da de alta un espacio físico en el inventario.

**Request**
```json
{
  "code": "A-201",
  "space_type": "CLASSROOM",
  "name": "Aula magna",
  "capacity": 60,
  "campus": "Sede Principal",
  "building": "A"
}
```

Solo `code` y `space_type` son obligatorios. **`capacity` puede quedar en `null`** y no es un
campo que se olvidó marcar obligatorio: un aula cuyo aforo nadie ha medido es un dato legítimo, y
un número inventado contamina la comprobación de aforo de la iteración 7.2 sin que nadie vuelva
a revisarlo.

El `code` se guarda recortado y en mayúsculas, y la comprobación de duplicado se hace **sobre el
código ya normalizado**. Sin eso, `a-201` y `A-201` serían dos filas para el mismo salón, y con
dos filas la restricción de doble reserva de la 7.2 no puede impedir nada: cree que son sitios
distintos.

**Response 201** — el espacio creado.

| Código HTTP | error.code | Situación |
|---|---|---|
| 409 | `DUPLICATE_SPACE_CODE` | Ya existe un espacio con ese código. `details.code` trae el código normalizado |

### GET /admin/spaces

Devuelve el inventario completo. Acepta `?space_type=CLASSROOM|LABORATORY|AUDITORIUM`.

**Sin paginar**, al contrario que el catálogo de materias: una institución tiene decenas o pocos
cientos de espacios, no miles, y quien va a asignar un aula necesita verlos todos.

### GET /admin/programs

Lista los programas académicos, para poder elegir cuál plan editar.

**Response 200**
```json
{
  "items": [
    { "id": "uuid", "code": "ISIS", "name": "Ingeniería de Sistemas", "total_semesters": 10 }
  ],
  "total": 1
}
```

### GET /admin/programs/{program_id}/plan

El plan de estudios de un programa cualquiera.

Se distingue de `GET /students/me/study-plan` en **quién elige el programa**, y esa diferencia
es de autorización: aquel devuelve siempre el plan de quien pregunta, y por eso no necesita rol.

**No trae el semáforo.** Aquel cruza el plan con el historial y la matrícula de una persona
concreta, y en esta pantalla no hay persona; `approved_credits` viene en `0`.

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `PROGRAM_NOT_FOUND` | El programa no existe |

### PUT /admin/programs/{program_id}/plan/{course_id}

Deja la materia en el plan con esos datos, esté o no.

**Request**
```json
{ "suggested_semester": 3, "is_mandatory": true }
```

Es un `PUT` y no un `POST` porque la operación es **idempotente**: la clave de `program_courses`
es la pareja `(programa, materia)`. Si añadir y editar fueran operaciones distintas, quien
administra tendría que saber de antemano cuál pedir, y la interfaz consultar el plan antes de
cada guardado solo para acertar con el verbo.

**Response 204.**

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `PROGRAM_NOT_FOUND` | El programa no existe |
| 404 | `COURSE_NOT_FOUND` | La materia no existe en el catálogo |

### DELETE /admin/programs/{program_id}/plan/{course_id}

Retira la materia del plan.

**Se rechaza si otra materia del plan la exige**, y esa es la razón de ser del endpoint. La clave
foránea de `program_course_requirements` apunta al plan con `ON DELETE CASCADE`, así que sacar
`MAT101` borraría en silencio el requisito «`MAT102` exige `MAT101`». La base no daría error;
nadie se enteraría hasta que alguien inscribiera Cálculo II sin haber visto Cálculo I.

**Response 204.**

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `COURSE_NOT_FOUND` | La materia no estaba en ese plan. Confirmar una operación que no hizo nada esconde el malentendido de quien la pidió |
| 409 | `COURSE_REQUIRED_BY_OTHERS` | Otras materias la exigen. `details.required_by` trae sus códigos, que es lo que permite saber qué requisito retirar primero |

La respuesta de `GET .../plan` **no lleva los campos del semáforo** —`status`,
`missing_prerequisites`, `missing_corequisites`— aunque el del estudiante sí. Aquí no hay persona
sobre la que calcularlos, así que saldrían siempre con su valor por defecto, y un
`status: "NOT_OFFERED"` en todas las materias se lee como un hecho sobre la oferta cuando solo
significa «no se calculó». Lleva en cambio `requirements` por materia, con el código, el nombre y
el tipo de cada requisito, que es lo que la pantalla de administración edita.

### PUT /admin/programs/{program_id}/plan/{course_id}/requirements/{required_course_id}

Deja el requisito cargado, o le cambia el tipo si ya estaba.

**Request**
```json
{ "requirement_type": "PREREQUISITE" }
```

`PUT` porque es idempotente: la clave de `program_course_requirements` es la terna
`(programa, materia, exigida)` y **no incluye el tipo**, así que volver a mandarlo con otro tipo lo
cambia en vez de duplicar la regla. Ese diseño es también el que impide declarar que una materia
es a la vez prerrequisito y correquisito de otra, dos reglas que se contradicen.

**Los requisitos son RETROACTIVOS y el plan de estudios no se versiona.** La decisión salió de
cómo se leen los dos tipos:

- Un **prerrequisito** se valida solo al inscribir. Creada la inscripción, nadie vuelve a
  comprobarlo, así que una regla nueva no puede romper una matrícula existente.
- Un **correquisito** se recalcula en cada lectura de las inscripciones, y solo las del período
  activo. Ahí está el único cambio con víctima posible.

**Response 204.**

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `PROGRAM_NOT_FOUND` | El programa no existe |
| 404 | `COURSE_NOT_FOUND` | Alguna de las dos materias no está en ese plan. Se comprueba aquí y no se deja a la clave foránea compuesta porque un fallo de restricción no dice cuál de las dos falta |
| 409 | `IMPOSSIBLE_REQUIREMENT_CYCLE` | Cerraría una vuelta con al menos un prerrequisito. `details.cycle` trae la vuelta completa: saber que hay un ciclo no dice qué arista sobra |
| 409 | `REQUIREMENT_WOULD_TRAP_ENROLLED` | Correquisito sobre una materia con matriculados y la ventana ya cerrada. `details` trae `enrolled_count` y `required_code` |

Un **ciclo de puros correquisitos es legítimo**: «`FIS101` y `LAB101` se cursan juntas» es la
forma normal de decir que dos materias van en bloque, y la exención de pares mutuos de la
iteración 6.2 lo hace inscribible. Lo que no se puede satisfacer es la mezcla: si en la vuelta hay
un prerrequisito, alguna materia tendría que estar aprobada antes de poder cursarse.

`REQUIREMENT_WOULD_TRAP_ENROLLED` **solo se lanza con la ventana cerrada**, y esa distinción es
la regla, no un matiz. Con la ventana abierta quien ya está inscrito ve el pendiente en
`GET /students/me/enrollments` y lo resuelve inscribiendo la materia que falta: el aviso ya existe
y llega solo. Con la ventana cerrada ve que le falta algo y no puede inscribir nada.

### DELETE /admin/programs/{program_id}/plan/{course_id}/requirements/{required_course_id}

Retira el requisito. **Response 204.**

No tiene la comprobación de matriculados que sí tiene cargarlo, y no es una omisión: relajar una
regla no puede dejar a nadie incompleto. Quien la cumplía sigue cumpliendo el plan, y quien no,
deja de estar bloqueado.

| Código HTTP | error.code | Situación |
|---|---|---|
| 404 | `COURSE_NOT_FOUND` | Ese requisito no estaba cargado |

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

## 7bis. Docente (requiere rol PROFESSOR)

El docente entra como ACTOR desde la Fase 9. Hasta la Fase 8 era solo un dato del catálogo —el
nombre de quien dicta un grupo— y no tenía cuenta.

Todas las rutas cuelgan de `/professors/me` y **resuelven el perfil desde el token**. No hay
ninguna ruta con un identificador de docente dentro: si la hubiera, cualquier docente podría
pedir la carga —y las notas— de otro, y la única defensa sería acordarse de comprobarlo en cada
endpoint.

**Un administrador NO puede entrar por aquí**, y es deliberado. Quien conoce la nota es quien
dictó la clase; dejar que la ponga cualquiera con permiso amplio borra esa responsabilidad.

### GET /professors/me/offerings

Los grupos que dicta quien pregunta, en la ventana activa.

**Response 200**
```json
{
  "period_code": "2025-2-V1",
  "academic_period": "2025-2",
  "items": [
    {
      "offering_id": "uuid",
      "course_id": "uuid",
      "course_code": "MAT101",
      "course_name": "Cálculo I",
      "credits": 4,
      "group_number": "01",
      "enrolled_count": 10,
      "total_capacity": 40,
      "schedule": [
        { "day_of_week": 1, "start_time": "08:00:00", "end_time": "10:00:00", "classroom": "A-201" }
      ]
    }
  ],
  "total": 1
}
```

Lleva `enrolled_count` y **no** `available_slots`, al contrario que `GET /courses/{id}/offerings`.
Al docente no le sirve saber cuántas plazas quedan —no va a matricular a nadie—; le sirve saber a
cuánta gente tiene enfrente, que es un número distinto aunque salga de los mismos datos. Tampoco
repite su propio nombre, que en el catálogo sí va porque allí lo lee quien busca dónde
matricularse.

**Sin período activo responde 200** con `items: []` y `period_code: null`, no un 404: entre
semestres no hay ventana abierta y eso es normal, mientras que un 404 diría que algo está roto.
`period_code` en `null` es lo que distingue ese caso de «hay semestre y no tengo carga», que se ve
igual —una lista vacía— y significa algo muy distinto.

| Código HTTP | error.code | Situación |
|---|---|---|
| 401 | `MISSING_TOKEN` | Sin cabecera `Authorization` |
| 403 | `PROFESSOR_REQUIRED` | La cuenta no tiene rol de docente. También le pasa a un ADMIN |
| 404 | `PROFESSOR_PROFILE_NOT_FOUND` | La cuenta tiene el rol pero ninguna fila de `professors` la apunta |

Los dos últimos se separan porque **se corrigen en sitios distintos**: el 403 cambiando el rol, el
404 dando de alta al docente y enlazando su cuenta. Un único código mandaría a la mitad de los
casos al sitio equivocado.

### GET /professors/me/offerings/{offering_id}/roster

La lista del grupo: quién está inscrito y qué nota lleva cada uno.

**Response 200**
```json
{
  "offering_id": "uuid",
  "course_code": "MAT101",
  "course_name": "Cálculo I",
  "group_number": "01",
  "entries": [
    {
      "student_id": "uuid",
      "student_code": "202500001",
      "full_name": "Ada Álvarez",
      "final_grade": "4.25",
      "graded_at": "2026-08-26T20:31:27Z"
    }
  ],
  "total": 1,
  "pending": 0
}
```

**`final_grade` en `null` es «todavía sin calificar», y NO es lo mismo que `"0.00"`.** Son
estados opuestos —uno es que falta trabajo, el otro es una nota reprobatoria— y con un cero por
defecto se verían igual. Es la misma razón por la que la columna es nullable.

Solo salen las inscripciones **vivas**. Quien canceló no cursó la materia, y ofrecerla en la
lista invitaría a calificar una fila que el servidor va a rechazar.

`pending` viene calculado para que la interfaz no tenga que recorrer la lista, y sobre todo para
que la pantalla del docente y el cierre del período de la 9.3 usen el mismo número.

### PUT /professors/me/offerings/{offering_id}/grades/{student_id}

Registra o corrige la nota final. **Response 204.**

**Request**
```json
{ "final_grade": "4.25" }
```

Escala de 0.0 a 5.0; aprueba desde 3.0. El rango se valida en tres capas —el schema de Pydantic,
el value object `Grade` y un `CHECK` de PostgreSQL— y no es redundancia por descuido: Pydantic da
el error de formato antes de tocar el dominio, `Grade` protege cualquier otro camino que escriba
una nota (el seed, una migración, un caso de uso futuro) y el `CHECK` es la red final. Es la misma
filosofía de defensas superpuestas que sostiene el control de cupos.

El redondeo es **HALF_UP**: `2.995` sube a `3.00` y aprueba. El redondeo bancario que Python trae
por defecto es correcto para promediar dinero y equivocado para decidir el semestre de alguien.

**LA NOTA SE GUARDA EN LA INSCRIPCIÓN, NO EN `academic_history`.** El historial es un registro
consolidado: lo que hay ahí decide prerrequisitos y aparece en el expediente. Escribir cada tecleo
del docente directamente allí haría irreversible una corrección tan normal como equivocarse de
fila. La consolidación es una operación aparte, de Registro Académico (iteración 9.3).

`PUT` porque es idempotente: volver a poner la misma nota deja el mismo estado. Por eso corregir
una nota mal tecleada es esta misma llamada y no una operación aparte que quien califica tenga que
recordar.

| Código HTTP | error.code | Situación |
|---|---|---|
| 403 | `OFFERING_NOT_ASSIGNED` | El grupo existe pero lo dicta otra persona |
| 404 | `OFFERING_NOT_FOUND` | El grupo no existe |
| 404 | `STUDENT_NOT_ENROLLED` | Ese estudiante no está en ese grupo |
| 409 | `GRADING_PERIOD_CLOSED` | El grupo es de un período que ya no es el activo |
| 409 | `ENROLLMENT_CANCELLED_CANNOT_GRADE` | Esa persona canceló la materia |
| 422 | — | La nota está fuera de la escala |

**Los cinco rechazos van separados a propósito**, y los dos primeros son el ejemplo claro: `403`
manda a hablar con Registro Académico y `404` manda a revisar la URL. Un único código dejaría a
cuatro de los cinco casos buscando donde no está el problema.

`GRADING_PERIOD_CLOSED` protege algo concreto: las notas de un semestre cerrado ya se usaron para
calcular prerrequisitos, y cambiarlas podría dejar a alguien cursando ahora mismo una materia que
dejaría de poder cursar.

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
