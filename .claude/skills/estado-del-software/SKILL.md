---
name: estado-del-software
description: Memoria viva del Sistema de Matrícula. Consúltala ANTES de escribir código, proponer un diseño o retomar el trabajo tras un corte, y ACTUALÍZALA al cerrar cada iteración. Contiene dónde vive cada pieza (backend, PostgreSQL, Redis), qué está construido y qué no, las decisiones ya tomadas que no se vuelven a discutir, y el protocolo de actualización. Úsala también cuando la pregunta sea "¿por qué está hecho así?" o "¿en qué punto vamos?".
---

# Estado del software — Sistema de Matrícula

> **Actualizada al cerrar la iteración 8.2 (formularios de períodos, materias y grupos).**
> Última verificación real: frontend con `npm run lint`, `type-check`, `test` (113 tests) y
> `build` en verde; backend sin cambios desde la 8.1 (579 tests, `mypy --strict` limpio sobre
> 162 archivos). Antes de esto:
> frontend sin cambios desde la 6.4 (lint, type-check, 94 tests y build en verde). La migración
> `0009` se aplicó sobre la base de desarrollo y dejó 21 espacios con CERO franjas huérfanas, y
> se comprobó contra la API real que un código inexistente responde `SPACE_NOT_FOUND` y que
> `  lab-01 ` resuelve a `LAB-01`. La migración `0010` liberó 18 franjas que ya estaban
> doblemente reservadas y se comprobó a mano que PostgreSQL rechaza el `INSERT` solapado y
> acepta la misma aula a la misma hora en OTRO período.
> El semáforo de la 6.3 se comprobó además contra la API real con dos cuentas del seed —una sin
> historial y otra con `MAT101` aprobada, que desbloquea `MAT102`—, verificando la promesa de la
> iteración: `POST /enrollments` rechaza con `PREREQUISITES_NOT_MET` justo lo que el plan marca
> `BLOCKED`, y acepta lo que marca `AVAILABLE`.

Este archivo es la memoria del proyecto entre sesiones. `CLAUDE.md` dice cómo se trabaja; esto
dice **en qué punto está el software y por qué está hecho así**. Si los dos se contradicen,
manda `CLAUDE.md` y hay que corregir este archivo.

## 1. Dónde vive cada cosa

Todo el desarrollo local corre en Docker Compose, proyecto `matricula` (`docker-compose.yml` en
la raíz). Nada se ejecuta en el host: los comandos van por `docker-compose exec backend ...`.

| Pieza | Dónde | Detalle que hay que recordar |
|---|---|---|
| Backend | contenedor `matricula-backend-1`, `http://localhost:8000` | FastAPI + uvicorn, código montado en `/app` con recarga en caliente. Etapa `dev` del Dockerfile (trae pytest, black, isort, mypy) |
| PostgreSQL | contenedor `matricula-postgres-1`, `localhost:5432` | Imagen `postgres:16`, base `matricula`, usuario `matricula`. Volumen `pgdata`. **Los tests usan otra base: `matricula_test`**, que crea y migra `tests/integration/conftest.py` |
| Redis | contenedor `matricula-redis-1`, `localhost:6379` | Imagen `redis:7`, base lógica **0** en desarrollo y **1** en los tests (`tests/conftest.py` reescribe la URL) |
| Migraciones | Alembic, dentro del backend | Los tests corren `alembic upgrade head`, nunca `create_all`: así prueban el esquema real, con triggers, índices parciales y `CHECK` |
| Configuración | `app/infrastructure/config/settings.py` (Pydantic Settings) | `DATABASE_URL`, `REDIS_URL` y `JWT_SECRET` son obligatorios; sin ellos la app no arranca. En AWS los inyecta Elastic Beanstalk desde Secrets Manager |
| Frontend | `frontend/`, `http://localhost:5173` | React 18 + TS + Vite. Corre en la máquina, NO en Docker. `npm run dev`. Habla con la API por `VITE_API_BASE_URL`; **hay que copiar `.env.example` a `.env.local`** (sin él, en desarrollo cae a `http://localhost:8000` con un aviso por consola; en un build de producción falla al arrancar). El 5173 es el único origen que la API autoriza por CORS en desarrollo |
| Despliegue en AWS | `deploy/aws/` | `Dockerrun.aws.json` (lo que lee Elastic Beanstalk) y el README con variables por ambiente, health checks, cuenta de conexiones a RDS y grupos de seguridad |

Comandos que se usan de verdad (equivalentes en el `Makefile`):

```bash
docker-compose up -d                                   # make dev
docker-compose exec backend pytest -q                  # make test
docker-compose exec backend pytest -m unit -q          # sin base de datos
docker-compose exec backend alembic upgrade head       # make migrate
docker-compose exec backend python -m app.infrastructure.seed   # make seed (idempotente)
docker-compose exec backend black app tests && docker-compose exec backend isort app tests
docker-compose exec backend mypy app                   # make lint
```

**Nunca corras dos suites a la vez.** Los tests de integración vacían tablas enteras de
`matricula_test` y comparten la base lógica 1 de Redis: dos `pytest` simultáneos se borran los
datos entre sí y fallan en sitios que no tienen nada que ver con el cambio que estés probando.

## 2. Arquitectura, en una pantalla

Hexagonal. Las dependencias apuntan siempre al centro.

```
interfaces/api/routers  →  application/use_cases  →  domain/
        ↓ (DI)                     ↑ (puertos)
interfaces/api/dependencies/di.py ─┴─→ infrastructure/ (SQLAlchemy, Redis, JWT)
```

- `di.py` es el **único** sitio donde un puerto se resuelve a un adaptador concreto.
- Los routers son delgados: traducen schema ↔ entidad/DTO y no deciden nada.
- Las excepciones de dominio se traducen a HTTP en **un solo mapa**, `_MAPEO_ERRORES` de
  `main.py`. Una excepción sin entrada ahí cae en `400 DOMAIN_ERROR`, así que al añadir una hay
  que registrarla.
- Formato de error universal: `{"error": {"code", "message", "details"}}`. Los `401` llevan
  además `WWW-Authenticate: Bearer`.

## 3. Las decisiones que ya están tomadas

No se vuelven a discutir sin una razón nueva. Cada una está explicada en el código, en el sitio
donde importa.

1. **El sobrecupo es imposible por dos defensas, no por una.** `try_reserve_slot` es un único
   `UPDATE ... WHERE enrolled_count < total_capacity` (sin lectura previa), y por debajo está el
   `CHECK (enrolled_count <= total_capacity)` de PostgreSQL.
2. **El descuento de cupo NO usa bloqueo optimista por `version`.** Se probó y no escala: con N
   transacciones sobre la misma fila solo gana una por ronda, y se rechazaban cupos que existían.
   `version` sigue existiendo y se usa donde la contención sí es rara: `update_capacity`.
3. **La disponibilidad de cupos nunca se cachea.** El catálogo sí (Redis, TTL 30 s, claves
   `catalog:v1:...`). El detalle de un grupo se sirve de caché salvo `enrolled_count`, que se
   relee siempre de PostgreSQL.
4. **La caché se invalida FUERA de la transacción y solo tras confirmarla.** Invalidar dentro y
   revertir después dejaría la caché repoblada con el valor viejo.
5. **La caché nunca hace fallar una petición.** Entrada ilegible o Redis caído ⇒ se va a
   PostgreSQL. El adaptador lleva cortacircuitos y por eso su instancia es única por proceso.
6. **Rol ADMIN declarado una vez, en el router**, no endpoint por endpoint.
7. **Los reportes se calculan en vivo**, agregando en SQL con `GROUP BY`. Nunca se cachean.
8. **Un grupo se abre siempre en el período activo**, que no viaja en la petición.
9. **Los códigos de materia se normalizan** en el value object `CourseCode` antes de comprobar
   duplicados; si no, `mat101` y `MAT101` convivirían.
10. **`/health` es liveness y `/health/ready` es readiness.** El ALB mira la primera; la segunda
    comprueba PostgreSQL y Redis y solo se consulta tras un despliegue. Poner dependencias en la
    del balanceador convierte una caída de RDS en una caída total.
11. **Los logs son JSON de una línea a stdout** en todo lo que no sea `dev`, porque los lee
    CloudWatch Logs Insights. Cada respuesta lleva `X-Request-ID`, que reutiliza el
    `X-Amzn-Trace-Id` del ALB cuando existe.
12. **El tamaño del pool de PostgreSQL es configurable por entorno.** El límite real es
    `max_connections` de RDS repartido entre todas las instancias del autoescalado.
13. **En el frontend, el estado del servidor lo gestiona TanStack Query**, los cupos no se
    consideran frescos nunca, las mutaciones no se reintentan solas y los errores se deciden
    por `error.code`, jamás por el mensaje.
14. **Los tests del frontend usan `happy-dom`, no `jsdom`.** jsdom sustituye el
    `AbortController` global por el suyo y el `fetch` de Node rechaza esa señal: con jsdom
    fallan TODAS las peticiones de los tests por un problema que no existe en el navegador.
15. **Los tokens: access en MEMORIA, refresh en `localStorage`.** El access token firma cada
    petición y es el que más daño hace si se filtra; al vivir en una variable de módulo, un
    script inyectado no puede leerlo. El refresh se persiste porque, si no, recargar la pestaña
    cerraría la sesión en plena matrícula. La cookie `httpOnly` se descartó: CloudFront y el
    balanceador son dominios distintos, así que sería una cookie de terceros. Todo en
    `frontend/src/features/auth/tokenStorage.ts`, el único archivo a reescribir si se unifican
    los dominios.
16. **La sesión se renueva un minuto ANTES de caducar**, y el refresh token se rota en cada
    renovación: hay que guardar siempre el nuevo. Esperar al 401 haría fallar una petición
    siempre, y si esa petición es la inscripción, falla en el peor momento.
17. **`RequireAuth` no es seguridad**, es honestidad de la interfaz. Lo que protege de verdad
    son los guardianes del backend. Al cerrar sesión se vacía la caché de TanStack Query: si no,
    la siguiente persona en el mismo navegador vería un instante los datos de la anterior.
18. **Los filtros del catálogo viven en la URL, no en `useState`.** Es lo que hace que el
    botón de atrás vuelva a la búsqueda anterior, que recargar no pierda lo escrito y que un
    enlace filtrado se pueda compartir. La búsqueda espera 300 ms antes de lanzarse.
19. **Los 409 de la inscripción NO son errores, son estados de la interfaz.**
    `frontend/src/features/enrollment/mensajes.ts` los traduce a un título («El grupo se
    llenó») y un detalle que dice qué hacer ahora. Se aprovechan los `details` del error:
    `SCHEDULE_CONFLICT` trae día y hora del cruce, `PREREQUISITES_NOT_MET` los códigos que
    faltan.
20. **No hay actualizaciones optimistas al inscribir.** El resultado depende de una carrera por
    el último cupo que solo PostgreSQL resuelve; pintar «inscrito» y retirarlo medio segundo
    después es peor que esperar. Tras inscribir o cancelar se invalidan a la vez las tres cosas
    que cambiaron: mis materias, mi horario y los cupos del catálogo.
21. **`GET /students/me/enrollments` existe aparte de `/me/schedule`** porque el horario no
    lleva el identificador de la inscripción, y sin él no se puede cancelar.
22. **El comprobante en PDF se genera al vuelo con ReportLab, nunca se almacena.** ReportLab
    y no WeasyPrint/wkhtmltopdf porque esas exigen librerías del sistema (Cairo, Pango, un
    navegador) que engordarían la imagen de Elastic Beanstalk. El renderizador es un puerto
    (`ReceiptRenderer`), así que el contenido se prueba sin generar un byte de PDF.
23. **El comprobante reutiliza `ListStudentEnrollmentsUseCase`**, no repite sus consultas: es
    lo que garantiza que el PDF y la pantalla «Mis materias» sumen los mismos créditos.
24. **La descarga del PDF va por `fetch`, no por un `<a href>`.** El endpoint exige
    `Authorization: Bearer` y un enlace no envía cabeceras; poner el token en la URL lo dejaría
    en el historial, en los registros del ALB y en la cabecera `Referer`.
25. **El catálogo se acota por defecto a la carrera del estudiante.** `GET /courses` sigue
    siendo público y sin filtro, pero la interfaz consulta `GET /students/me/study-plan` y usa
    ese programa. Antes se listaba todo y la persona descubría el `403 COURSE_NOT_IN_PROGRAM`
    al pulsar «Inscribir»: la regla del servidor era correcta, la interfaz ofrecía algo que
    iba a fallar.
26. **`suggested_semester` e `is_mandatory` viven en `program_courses`, no en `Course`.** La
    misma materia puede ser de primer semestre y obligatoria en una carrera, y de tercero y
    electiva en otra. Por eso `GET /courses` no puede devolverlos y el plan de estudios sí.
27. **Un requisito académico pertenece al PLAN DE ESTUDIOS, no al catálogo.**
    `program_course_requirements` sustituyó a `course_prerequisites` (migración `0007`). La
    tabla anterior afirmaba que MAT102 exige MAT101 en toda la institución, y eso deja de ser
    cierto en cuanto una materia entra en dos planes. Sus claves foráneas son COMPUESTAS
    contra `program_courses`, así que declarar un requisito sobre una materia ajena a la
    carrera es imposible por construcción.
28. **El correquisito se valida contra las inscripciones vivas, el prerrequisito contra el
    historial.** Son dos servicios de dominio distintos porque son dos reglas distintas: una
    mira un hecho cerrado y la otra, la matrícula que la persona está armando ahora.
29. **Un correquisito MUTUO no exige estar ya inscrito.** Si A exige B y B exige A, pedir que
    la otra esté dentro antes hace que la primera falle siempre y el bloque quede fuera de la
    matrícula por cualquier camino. Se valida el conjunto: las materias unidas por
    correquisitos recíprocos forman un bloque y cualquiera entra primero. El precio, asumido:
    entre la primera y la segunda inscripción la matrícula queda incompleta, y hacerlo visible
    le toca a la 6.3. El endpoint de inscripción múltiple se descartó por cambiar el contrato
    de la operación más crítica del sistema.
30. **`GET /courses/{id}` no responde requisitos sin `program_id`.** Devuelve las dos listas
    vacías y `program_id: null`. Devolver la unión de todos los planes no es cierta en ninguna
    carrera concreta y le mostraría a un estudiante de Derecho los requisitos de Ingeniería.
    Por eso `GET /students/me/study-plan` empezó a devolver `program_id`: es lo que el
    frontend envía.
31. **La regla de correquisitos vale en las DOS direcciones.** Inscribir la comprobaba y
    cancelar no, así que bastaba con cancelar la materia exigida para quedar en un estado que
    inscribir jamás habría permitido. Cancelar se rechaza (`COREQUISITE_DEPENDENCY`) mientras
    una materia inscrita dependa de esta en un solo sentido, y arrastra el BLOQUE ENTERO cuando
    la dependencia es mutua: rechazarla ahí dejaría las dos imposibles de abandonar. Las dos
    caras viven en el mismo `CorequisiteValidator` para que no puedan divergir otra vez.
32. **`DELETE /enrollments/{id}` devuelve 200 con lo que canceló, no 204.** Con el arrastre del
    bloque, un 204 haría desaparecer dos materias de la pantalla tras pulsar «Cancelar» en una
    sola, y eso se lee como una avería. El aviso se pinta en la PÁGINA y no en la fila: la fila
    cancelada se desmonta en cuanto llega la respuesta.
33. **La matrícula incompleta se permite, pero no se esconde.** `GET /students/me/enrollments`
    devuelve `pending_corequisites` por materia. Es el precio de dejar que el bloque mutuo entre
    de una en una, y sin hacerlo visible ese estado transitorio se vuelve permanente.
34. **`ix_program_course_requirements_required` no es opcional.** La consulta inversa —«qué
    materias exigen a esta»— filtra por `(program_id, required_course_id)`, que NO es prefijo de
    la clave primaria. Corre dentro de la transacción que libera un cupo mientras las
    inscripciones compiten por él: el peor sitio para un recorrido de tabla.
35. **El semáforo del plan NO reimplementa las reglas: las delega.**
    `StudyPlanStatusResolver` llama a `PrerequisiteValidator.missing` y
    `CorequisiteValidator.missing`, los mismos objetos que deciden si una inscripción se
    acepta. Por eso los dos validadores tienen ahora la regla partida en dos: `missing`
    consulta y `validate` es `missing` seguido de un `raise`. Sus consumidores son opuestos —la
    inscripción quiere que falle, el semáforo quiere saber qué falta en decenas de materias sin
    una excepción por cada una— y el día que discrepen la pantalla ofrecerá lo que el servidor
    rechaza.
36. **El semáforo trata «se puede inscribir a la vez» como «está inscrito».** Le pasa a
    `CorequisiteValidator.missing` las materias inscritas MÁS las ofertadas. No es un abuso de
    la firma: al inscribir importa si el correquisito ya está dentro, y al pintar el plan
    importa si podría estarlo. Sin eso, una materia cuyo correquisito no tiene grupos saldría
    disponible y la inscripción la rechazaría.
37. **No existe un estado «de otro semestre»**, aunque la hoja de ruta lo nombrara. El semestre
    sugerido es una sugerencia y no una restricción —lo dice `program_courses`—, así que
    convertirlo en estado afirmaría un impedimento que el sistema no aplica. La pantalla agrupa
    por semestre, que es lo que esa idea aportaba.
38. **`GET /students/me/study-plan` no se cachea, y ahora se ve por qué.** Dejó de devolver el
    plan para devolver el plan CRUZADO con el historial y la matrícula de quien pregunta: dos
    estudiantes de la misma carrera reciben cuerpos distintos y el de cada uno cambia con cada
    inscripción. Tampoco falla fuera de la ventana de matrícula: «qué me falta para graduarme»
    se pregunta todo el año, y sin período activo lo que cumple requisitos sale `NOT_OFFERED`.
39. **El aula es una entidad, no un texto, y el contrato público no se enteró.**
    `spaces` + `schedule_blocks.space_id` sustituyen a `classroom` (migración `0009`). Un texto
    no puede estar ocupado: con `A-201` y `A201` como cadenas distintas no había forma de
    impedir la doble reserva. Las respuestas siguen exponiendo `classroom` con el código del
    aula —quien lee un horario quiere leer «A-201»—, y solo la ENTRADA cambió: `POST
    /admin/offerings` recibe `space_code`, se resuelve en el caso de uso y un código
    desconocido da `404 SPACE_NOT_FOUND` en vez de guardarse como una cadena sin significado.
40. **`spaces.capacity` admite nulos a propósito.** Los espacios que nacieron del traslado de
    textos no traían aforo, e inventarlo habría creado el número contra el que la 7.2 valida.
    `Space.fits()` devuelve `None` cuando no se sabe: «no sé» no es «sí» ni «no».
41. **La doble reserva se impide con DOS defensas, como el sobrecupo.**
    `SpaceConflictDetector` da el mensaje —qué aula, a qué hora y qué grupo la ocupa— y la
    restricción de exclusión `GiST` de la migración `0010` da la garantía. Quitar cualquiera
    deja el sistema peor: sin la restricción, dos peticiones simultáneas reservan la misma aula;
    sin el detector, esa carrera perdida se presenta como un 500.
42. **`schedule_blocks.enrollment_period_id` es una copia deliberada.** Una restricción de
    exclusión solo mira columnas de su tabla, y sin el período prohibiría reutilizar un aula el
    semestre siguiente. La clave foránea COMPUESTA impide que la copia mienta.
43. **El seed reparte aulas comprobando ocupación** (`_aula_libre`). Antes lo hacía en rueda
    ciega a propósito; con la restricción puesta, ese seed ya no se puede ejecutar.
44. **La disponibilidad de espacios mide con la MISMA regla que el rechazo.**
    `GET /admin/spaces/available` usa el solapamiento estricto de `SpaceConflictDetector` y el
    rango `[)` de la restricción. Si divergieran, ofrecería aulas que la apertura del grupo
    rechaza —o escondería las que acepta—, que es la contradicción que la Fase 6 se dedicó a
    eliminar. Un aula sin aforo registrado aparece aunque se pida un mínimo: es la misma
    decisión que `Space.fits` devolviendo `None`.
45. **`POST /auth/refresh` devuelve la CUENTA, no solo los tokens.** Es el endpoint que
    restaura la sesión al recargar, y sin ese dato el frontend recuperaba el acceso sin saber
    con qué rol. Las rutas `/admin` habrían expulsado a un administrador legítimo en cuanto
    refrescara la pestaña. El caso de uso ya cargaba el usuario para comprobar que sigue
    activo: devolverlo no cuesta una consulta más.
46. **`RequireAdmin` no es seguridad, es honestidad**, igual que `RequireAuth`. Lo que protege
    los datos es `require_admin` en el router del backend. Sin el guardián, un estudiante que
    escriba `/admin` vería un panel llenándose de 403 sin entender por qué.
47. **El armazón de administración va DENTRO del layout general**, no en su lugar: duplicar
    cabecera, pie, enlace de salto y menú de cuenta para cambiar solo la navegación sería copiar
    cuatro decisiones de accesibilidad ya tomadas. Lo propio es el `nav`, con `aria-label`
    porque hay dos landmarks de navegación en la página.
48. **El estado de la API vuelve, y solo en el panel de administración.** Es donde la 6.4 dijo
    que tenía sentido operativo: quien administra sí puede actuar si la API cae en plena
    matrícula, y ver el ambiente evita tocar cupos reales creyendo estar en pruebas.
49. **Los formularios de administración NO validan reglas de negocio.** Comprueban que los
    campos estén llenos y nada más: si el aula está libre, si el cupo no baja de los inscritos o
    si el horario se cruza lo decide el servidor, y `admin/mensajes.ts` traduce lo que responde.
    Duplicar esas reglas en el navegador garantiza que un día discrepen, que es el error que la
    Fase 6 se dedicó a eliminar.
50. **`admin/mensajes.ts` existe por la misma razón que el del estudiante, con otro público.**
    Allí los 409 son estados normales de una matrícula disputada; aquí son datos mal
    introducidos, y el mensaje decide si quien administra corrige en diez segundos o abre un
    ticket. Cada uno dice qué pasó y qué hacer, con los `details` del error: qué grupo ocupa el
    aula, cuántos hay inscritos, los dos números del aforo.
51. **El formulario de grupos no pide el docente**, aunque la API lo acepte. No existe endpoint
    para listar profesores, así que el campo solo podría ser un UUID escrito a mano: causaría
    más errores de los que evita. `professor_id` es opcional y se asigna después.
52. **El listado de materias de administración reutiliza `GET /courses`**, el mismo endpoint
    público del estudiante. Un endpoint gemelo solo añadiría un sitio donde las dos listas
    podrían acabar diciendo cosas distintas. Eso sí, aquí se ve el catálogo COMPLETO: al
    estudiante se le acota porque solo puede inscribir lo de su plan (6.1), y quien administra
    necesita ver todo para no crear dos veces la misma materia.
53. **El estado de la API no se le muestra al estudiante.** El recuadro de la pantalla de
    inicio y el indicador de la cabecera eran andamiaje de la 5.1, útil cuando no había
    pantallas reales y no se distinguía «la API está caída» de «mi código está mal». Al
    estudiante no le sirve —no puede hacer nada con un punto rojo— y ver el ambiente o un
    número de versión en la primera pantalla de su matrícula genera desconfianza. Cuando la API
    falla, quien lo dice es la operación que falló, con lo que hay que hacer al respecto: eso
    ya lo resuelve `mensajes.ts` en cada flujo. La 6.4 retiró las dos y BORRÓ la funcionalidad
    `features/health` del frontend en vez de dejarla sin renderizar, por la regla de oro de que
    cada archivo tiene un propósito; vive en el commit `3315eeb`, del que
    `git show 3315eeb:frontend/src/features/health/components/ServiceStatus.tsx` la recupera si
    la 8.1 la quiere de base. El endpoint `/health` del backend no se toca: lo
    consume el ALB.
54. **CORS declara orígenes exactos, nunca `*`.** El frontend vivirá en CloudFront, otro dominio;
    la API acepta credenciales y con ellas el comodín ni siquiera es válido.

## 4. Qué está construido

| Fase | Estado | Endpoints |
|---|---|---|
| 0 — Fundación | ✅ | `/health` |
| 1 — Autenticación | ✅ | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `GET /students/me` |
| 2 — Catálogo | ✅ | `GET /courses`, `/courses/{id}`, `/courses/{id}/offerings`, `/offerings/{id}`, `/enrollment-periods/current` |
| 3 — Inscripción | ✅ | `POST /enrollments`, `DELETE /enrollments/{id}`, `GET /students/me/schedule` |
| 4 — Admin y reportes | ✅ | ver desglose abajo |
| Preparación para la nube | ✅ | `/health/ready`, CORS, logs JSON, `X-Request-ID`, pool configurable, `deploy/aws/` |
| 5 — Frontend y comprobante | ✅ | 5.1 fundación · 5.2 autenticación · 5.3 catálogo · 5.4 inscripción y horario · 5.5 comprobante PDF |
| 6 — Reglas por carrera | ✅ | `GET /students/me/study-plan` con semáforo, ruta `/plan` en el frontend |

**Fase 8 — Interfaz de administración** (en curso): 8.1 estructura, acceso y panel ✅
(`ca86677`) · 8.2 períodos, materias y grupos ✅ (esta iteración) · 8.3 planes de estudio y
espacios · 8.4 reportes visuales.

**Fase 7 — Aulas y espacios físicos: COMPLETA.** 7.1 el espacio como entidad ✅ (`804fe31`) ·
7.2 doble reserva imposible ✅ (`642ee0a`) · 7.3 consulta de disponibilidad ✅ (esta iteración).

Lo siguiente es la **Fase 8 — Interfaz de administración**. No estaba en lo que pediste y la
hoja de ruta la pone ahí a propósito: todo lo que viene después —expediente, comunicaciones,
reportes— lo hace una persona de Registro Académico, y ahora mismo solo puede hacerlo
escribiendo JSON en Swagger. Sin esa fase, cada funcionalidad nueva nace inutilizable para
quien debe usarla.

**Fase 6 — Reglas académicas por carrera: COMPLETA.** 6.1 catálogo acotado ✅ (`c6782c0`) ·
6.2 prerrequisitos y correquisitos por plan ✅ (`0c0131b`) ·
6.2.1 consistencia del bloque al cancelar ✅ (`f2070a5`) ·
6.3 semáforo del plan ✅ (`3315eeb`) · 6.4 limpieza de la interfaz del
estudiante ✅ (esta iteración).

Lo siguiente es la **Fase 7 — Aulas y espacios físicos**: hoy el aula es un texto libre en
`schedule_blocks.classroom` y nada impide la doble reserva. Se cierra con una restricción de
exclusión GiST de PostgreSQL sobre el rango horario, la misma filosofía de dos defensas que
impide el sobrecupo.

El plan completo de las fases 6 a 10 está en el artefacto «Hoja de ruta FlexGrade».
Aprovisionar AWS sigue pendiente (ver `deploy/aws/README.md`).

Desglose de la Fase 4 por iteraciones (la numeración es nuestra; los documentos solo describen
la fase completa):

| Iteración | Entregable | Commit |
|---|---|---|
| 4.1 | Autorización por rol y formato de error unificado | `07b3215` |
| 4.2 | Ventanas de matrícula: crear, activar, listar | `346915d` |
| 4.3 | Catálogo y cupos: `POST /admin/courses`, `POST /admin/offerings`, `PUT /admin/offerings/{id}/capacity` | `34005b8` |
| 4.4 | Reportes: `GET /admin/reports/enrollments`, `GET /admin/reports/occupancy` | esta iteración |

Ausencias **intencionales** (no son deuda, no las implementes por iniciativa propia): la lista
de espera automática — `WAITLISTED` existe en el enum pero ninguna operación lo produce.

Ausencias que sí son deuda, pendientes de decidir cuándo se pagan:

- **DECISIÓN DE NEGOCIO PENDIENTE, para la iteración 8.3: ¿los requisitos son retroactivos?**
  Cuando exista la pantalla para editar el plan de estudios, alguien podrá añadir un
  correquisito a mitad de semestre y dejar incompletas matrículas ya hechas. Hoy no puede
  ocurrir por el producto —ningún endpoint de administración toca
  `program_course_requirements`—, y si se escribe a mano el sistema aguanta: se comprobó que
  `pending_corequisites` lo detecta solo y que el estudiante no queda atrapado (puede cancelar
  e inscribir). Lo único que falta es AVISARLE. Las dos respuestas legítimas son
  **retroactivo** —la regla nueva aplica a todos, y hay que notificar a quien quede
  incompleto, lo que depende del canal de avisos de la fase 10— y **no retroactivo** —quien ya
  matriculó conserva las reglas del momento, lo que obliga a versionar el plan de estudios y
  es un cambio de modelo, no un aviso—. 8.3 crea la forma de provocar el problema, así que es
  la iteración que debe traer la decisión tomada.

- **Rate limiting.** `API.md` fija límites por endpoint (login 5/min por IP, inscripción 30/min,
  catálogo 120/min, admin 60/min) y no hay nada implementado. Con varias instancias detrás del
  ALB, un contador en memoria no sirve: o AWS WAF con reglas por IP, o un contador en Redis para
  los límites por usuario.
- **Autenticación propia frente a Cognito.** El documento del proyecto nombra Cognito; el código
  emite y valida sus propios JWT con bcrypt. `AuthService` es un puerto, así que cambiarlo sería
  escribir un adaptador nuevo y tocar `di.py`, sin rozar el dominio. Decisión pendiente.
- **`GET /enrollment-periods` público.** `API.md` sección 5 lo documenta como listado paginado
  de períodos; el único listado que existe es `GET /admin/enrollment-periods`, que exige rol
  ADMIN.
- **`GET /students/me/history`.** Documentado en `API.md` sección 2, sin implementar. No lo
  necesita ninguna pantalla todavía.
- **El seed no comparte ninguna materia entre programas.** El esquema sí lo admite
  (`program_courses` tiene clave primaria compuesta), pero los datos de ejemplo dan a cada
  programa materias propias, así que ese camino no se ejercita nunca. La fixture `catalogo`
  de los tests de integración SÍ lo hace desde la 6.2 —dos planes que comparten MAT101 y
  MAT102 con reglas distintas—, que es donde se comprueba que los requisitos dependen del
  plan.
- **No hay endpoint de administración para los requisitos.** Se cargan por el seed o a mano.
  `POST /admin/courses` crea la materia y nada más.

## 5. Mapa rápido del código

```
backend/app/
├── domain/            entidades, value objects, servicios y excepciones. Sin dependencias
├── application/
│   ├── ports/         interfaces (repositorios, caché, auth, unit of work)
│   ├── dtos/          solo cuando el resultado compone varios agregados
│   └── use_cases/     auth · catalog · enrollment · admin
├── infrastructure/    SQLAlchemy (models + repositories), Redis, JWT, settings, seed
└── interfaces/api/    routers · schemas · dependencies (auth + di)

backend/tests/
├── unit/          sin base de datos. `doubles.py` (dobles de los puertos) y `factories.py`
├── integration/   contra PostgreSQL y Redis reales. `conftest.py` trae la fixture `catalogo`
└── e2e/

frontend/src/
├── app/            proveedores, rutas y layout: la forma de ESTA aplicación
├── components/ui/  piezas visuales reutilizables (Button, Card, StatusDot)
├── features/       una carpeta por funcionalidad, con su API, sus hooks y sus pantallas
├── lib/            cliente HTTP, errores de la API y configuración de TanStack Query
└── test/           MSW y el render con proveedores
```

El CI del frontend (`frontend-ci` en `ci.yml`) se activa solo porque existe
`frontend/package.json`, y ejecuta `lint`, `type-check`, `test` y `build`. Si se renombra
alguno de esos scripts, el job falla.

**Las acciones se fijan por versión MAYOR y estan en la que corre sobre Node 24**
(`checkout@v5`, `setup-python@v6`, `setup-node@v5`, `gitleaks-action@v3`). GitHub retira Node 20
de los runners en septiembre de 2026; hasta entonces avisa en cada corrida. Los bloques de AWS y
Docker que siguen COMENTADOS a la espera de aprovisionar la nube conservan versiones antiguas
—`aws-actions/*`, `docker/*`— y hay que revisarlas al descomentarlas, porque nadie las ha
ejecutado nunca.

**Este repositorio tiene `.gitattributes` y no es decorativo.** Fija `text=auto` y `eol=lf` para
lo que ejecuta un runner Linux (`.sh`, `.yml`, `Dockerfile`, `Makefile`). Sin él, que un archivo
quede en LF o en CRLF dependía del `core.autocrlf` de cada máquina: en Windows, `deploy-prod.yml`
aparecía permanentemente como modificado mientras `git diff` no mostraba una sola línea de
diferencia, y `git update-index --really-refresh` respondía «needs update» sin más explicación.

**`deploy-dev.yml` y `deploy-staging.yml` llaman a `ci.yml` con `uses:`, y eso les obliga a
conceder permisos.** Un workflow llamado no puede pedir más de lo que le da quien lo llama:
`backend-ci` necesita `pull-requests: write` para que gitleaks comente el hallazgo en el PR, y
mientras el llamador solo declaró `contents: read` la corrida fallaba **al arrancar**, sin
crear un solo job. Ese fallo es el peor de todos para diagnosticar: no hay logs, no hay check
runs, y `gh run view` solo dice «likely failed because of a workflow file issue». El mensaje
real está en la página web de la corrida. El permiso se concede en el job `ci:` y no a nivel de
workflow, para que los pasos de despliegue sigan sin poder escribir en pull requests.

Al añadir un puerto hay que tocar cuatro sitios: el puerto, el adaptador SQL, `di.py` y el
doble en `tests/unit/doubles.py`. Olvidar el último rompe todos los tests que instancian ese
doble, porque la clase abstracta deja de poder construirse.

## 6. Protocolo de actualización

**Al cerrar cada iteración, antes del commit**, revisa este archivo y actualiza:

1. La línea de "Actualizada al cerrar…" del encabezado, con las cifras reales de `pytest` y
   `mypy` que acabas de ver (no de memoria).
2. La tabla de fases y el desglose de iteraciones, con el hash del commit.
3. La sección 3 **solo si se tomó una decisión nueva** que cambie cómo se construye algo. Una
   decisión que ya está ahí no se reescribe.
4. La sección 1 si cambió dónde vive algo: puerto, servicio, base de datos, variable obligatoria.

Reglas para que este archivo siga sirviendo:

- **Nada que el repositorio ya diga mejor.** Aquí no se copian firmas de funciones, esquemas de
  tablas ni contratos de endpoints: para eso están `API.md`, `DATA_MODEL.md` y el código.
- **Cada afirmación, verificada.** Si dices que algo está hecho, es porque lo viste pasar, no
  porque el plan lo prometía.
- **Corrige lo que se quedó viejo.** Una línea desactualizada aquí es peor que no tenerla:
  se lee como si fuera cierta.
