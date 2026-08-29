---
name: estado-del-software
description: Memoria viva del Sistema de Matrícula. Consúltala ANTES de escribir código, proponer un diseño o retomar el trabajo tras un corte, y ACTUALÍZALA al cerrar cada iteración. Contiene dónde vive cada pieza (backend, PostgreSQL, Redis), qué está construido y qué no, las decisiones ya tomadas que no se vuelven a discutir, y el protocolo de actualización. Úsala también cuando la pregunta sea "¿por qué está hecho así?" o "¿en qué punto vamos?".
---

# Estado del software — Sistema de Matrícula

> **Actualizada al cerrar la 9.4 con su PANTALLA. Con ella la Fase 9 queda COMPLETA.** En la
> misma sesión se migró el repositorio entero de AWS a Azure (decisión 55).
> Última verificación real: frontend con `npm run lint`, `type-check`, `build` y `test`
> (**169 tests en 20 archivos**) en verde; backend con `black --check`, `isort --check-only`,
> `mypy` (limpio sobre 178 archivos) y `pytest` (**658 tests**) en verde tras la migración. Los
> cuatro workflows de despliegue vuelven a ser YAML válido. El expediente se comprobó además
> **contra la API real** con `estudiante01@tdea.edu.co` del seed: las notas llegan como cadena
> (`"3.60"`), y el ponderado del semestre (`3.60`) NO coincide con la media simple (`3.52`),
> que es justo lo que la pantalla no debe recalcular.
> **Dos avisos de método de esta sesión.** Los 12 errores de integración que aparecieron en una
> corrida intermedia no eran del cambio: venían de haber matado un `pytest` a media ejecución,
> que deja sucia `matricula_test`. Repetida sin nada más corriendo, verde — es la regla de la
> sección 1, nunca dos suites a la vez. Y `docencia.test.tsx` empezó a fallar al añadir un
> archivo de test más: no era el cambio, era una carrera latente suya —el `<nav>` existe antes
> de que llegue el rol, y el enlace se consultaba de forma síncrona—. Se arregló esperándolo, y
> las comprobaciones de AUSENCIA de un enlace de rol se anclan ahora a la espera de otro que sí
> debe estar; sin ese anclaje pasan aunque la regla se rompa. Antes de esto:
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
| Configuración | `app/infrastructure/config/settings.py` (Pydantic Settings) | `DATABASE_URL`, `REDIS_URL` y `JWT_SECRET` son obligatorios; sin ellos la app no arranca. En Azure los inyecta Azure App Service desde Key Vault |
| Frontend | `frontend/`, `http://localhost:5173` | React 18 + TS + Vite. Corre en la máquina, NO en Docker. `npm run dev`. Habla con la API por `VITE_API_BASE_URL`; **hay que copiar `.env.example` a `.env.local`** (sin él, en desarrollo cae a `http://localhost:8000` con un aviso por consola; en un build de producción falla al arrancar). El 5173 es el único origen que la API autoriza por CORS en desarrollo |
| Despliegue en Azure | `deploy/azure/` | `app-settings.example.json` (las opciones de aplicación del App Service, con los secretos como referencias `@Microsoft.KeyVault(...)`) y el README con variables por ambiente, health checks, ranuras de despliegue, cuenta de conexiones y reglas de red |

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
10. **`/health` es liveness y `/health/ready` es readiness.** El Application Gateway mira la primera; la segunda
    comprueba PostgreSQL y Redis y solo se consulta tras un despliegue. Poner dependencias en la
    del balanceador convierte una caída de PostgreSQL Flexible Server en una caída total.
11. **Los logs son JSON de una línea a stdout** en todo lo que no sea `dev`, porque los lee
    Log Analytics. Cada respuesta lleva `X-Request-ID`, que reutiliza la traza que ya venía
    puesta desde el borde: `X-Azure-Ref` (Front Door) y, si no, `traceparent`. El orden es de
    FUERA hacia dentro porque `X-Azure-Ref` es el único valor que aparece en los registros de
    Front Door.
12. **El tamaño del pool de PostgreSQL es configurable por entorno.** El límite real es
    `max_connections` del Flexible Server repartido entre todas las instancias del autoescalado.
13. **En el frontend, el estado del servidor lo gestiona TanStack Query**, los cupos no se
    consideran frescos nunca, las mutaciones no se reintentan solas y los errores se deciden
    por `error.code`, jamás por el mensaje.
14. **Los tests del frontend usan `happy-dom`, no `jsdom`.** jsdom sustituye el
    `AbortController` global por el suyo y el `fetch` de Node rechaza esa señal: con jsdom
    fallan TODAS las peticiones de los tests por un problema que no existe en el navegador.
15. **Los tokens: access en MEMORIA, refresh en `localStorage`.** El access token firma cada
    petición y es el que más daño hace si se filtra; al vivir en una variable de módulo, un
    script inyectado no puede leerlo. El refresh se persiste porque, si no, recargar la pestaña
    cerraría la sesión en plena matrícula. La cookie `httpOnly` se descartó: Azure Front Door y
    el Application Gateway son dominios distintos, así que sería una cookie de terceros. Todo en
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
    navegador) que engordarían la imagen de Azure App Service. El renderizador es un puerto
    (`ReceiptRenderer`), así que el contenido se prueba sin generar un byte de PDF.
23. **El comprobante reutiliza `ListStudentEnrollmentsUseCase`**, no repite sus consultas: es
    lo que garantiza que el PDF y la pantalla «Mis materias» sumen los mismos créditos.
24. **La descarga del PDF va por `fetch`, no por un `<a href>`.** El endpoint exige
    `Authorization: Bearer` y un enlace no envía cabeceras; poner el token en la URL lo dejaría
    en el historial, en los registros del Application Gateway y en la cabecera `Referer`.
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
    consume el Application Gateway.
54. **CORS declara orígenes exactos, nunca `*`.** El frontend vivirá en Azure Front Door, otro
    dominio; la API acepta credenciales y con ellas el comodín ni siquiera es válido.
55. **La nube del proyecto es AZURE, no AWS.** El documento de la Fase I cambió de proveedor y el
    repositorio se migró entero: `deploy/azure/`, los cuatro workflows de despliegue, la
    documentación y los comentarios del código. El mapeo, para no volver a discutirlo: App
    Service (era Elastic Beanstalk), Azure Database for PostgreSQL Flexible Server (RDS), Azure
    Cache for Redis (ElastiCache), Azure Storage + Front Door (S3 + CloudFront), Application
    Gateway con WAF (ALB), Key Vault (Secrets Manager), Azure Monitor y Log Analytics
    (CloudWatch), Microsoft Entra External ID (Cognito), ACR (ECR), VNet con subredes
    públicas/privadas y NAT Gateway (VPC). **El código de la aplicación no tenía acoplamiento
    real con AWS**: todo lo específico llegaba por variable de entorno. La única línea funcional
    que cambió fue la cabecera de traza del middleware de logs. El `.docx` del proyecto no se
    versiona: `*.docx` está en `.gitignore` porque es binario, git no lo puede fusionar y cada
    guardado reescribe el archivo entero.

## 4. Qué está construido

| Fase | Estado | Endpoints |
|---|---|---|
| 0 — Fundación | ✅ | `/health` |
| 1 — Autenticación | ✅ | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `GET /students/me` |
| 2 — Catálogo | ✅ | `GET /courses`, `/courses/{id}`, `/courses/{id}/offerings`, `/offerings/{id}`, `/enrollment-periods/current` |
| 3 — Inscripción | ✅ | `POST /enrollments`, `DELETE /enrollments/{id}`, `GET /students/me/schedule` |
| 4 — Admin y reportes | ✅ | ver desglose abajo |
| Preparación para la nube | ✅ | `/health/ready`, CORS, logs JSON, `X-Request-ID`, pool configurable, `deploy/azure/` |
| 5 — Frontend y comprobante | ✅ | 5.1 fundación · 5.2 autenticación · 5.3 catálogo · 5.4 inscripción y horario · 5.5 comprobante PDF |
| 6 — Reglas por carrera | ✅ | `GET /students/me/study-plan` con semáforo, ruta `/plan` en el frontend |
| 9 — Cierre del ciclo | ✅ | docente, notas, consolidación y `GET /students/me/history` con la ruta `/expediente` |

**Fase 9 — Cierre del ciclo académico: COMPLETA.** 9.1 el docente como actor ✅
(`8fe425c`) · 9.2 registro de notas ✅ (`75bc0d6`) · 9.3 cierre y consolidación del período ✅
(`0c6f7d0`, **incluye la 9.5**) · 9.4 expediente del estudiante ✅ (backend `4c2ba2b`,
**pantalla en esta iteración**).

De la 9.4, lo que no se vuelve a discutir:

- **Los promedios son PONDERADOS POR CRÉDITOS**, el de cada semestre y el acumulado. Con media
  simple, un `4.50` en una materia de 4 créditos y un `2.50` en una de 2 darían `3.50`;
  ponderado da `3.83`. Es la cifra que decide una beca y la que aparece en un certificado: una
  media simple no coincidiría con el oficial, y quien la viera la tomaría por buena.
- **El expediente muestra lo perdido igual que lo aprobado**, y la materia repetida aparece las
  dos veces, cada una en su semestre. Es justo lo que permite el `UNIQUE (student_id, course_id,
  academic_period)`.
- **Un expediente vacío es una respuesta legítima**, no un 404: quien acaba de ingresar todavía
  no ha cerrado ningún semestre.
- `find_by_student` trae TODAS las filas, al contrario que `find_approved_course_ids`, que
  filtra porque responde otra pregunta: «qué habilita esta persona», no «qué ha cursado».

De la PANTALLA de la 9.4 (`frontend/src/features/transcript/`, ruta `/expediente`):

- **Las notas y los promedios se quedan en `string` de punta a punta.** El backend los modela
  con `Decimal` y los serializa con dos decimales exactos —comprobado contra la API real: llegan
  como `"3.60"`, no como número—. Convertirlos a `number` en el cliente desharía esa decisión en
  el último paso: `4.00` se pintaría como `4` y dejaría de coincidir con el certificado oficial.
  Es la misma regla que la 9.2 fijó para el `final_grade` del listado del docente.
- **La pantalla no recalcula NINGÚN promedio.** Con los datos del seed, el ponderado del semestre
  da `3.60` y la media simple `3.52`: son cifras distintas, y la segunda no coincide con ningún
  documento de la institución. Un test lo fija con un caso donde las dos difieren, así que
  reintroducir la cuenta en el cliente rompe la suite.
- **Es una TABLA, no una rejilla de tarjetas.** Un expediente se lee comparando filas, se copia
  a un correo y se recorre con lector de pantalla saltando por columnas. Va dentro de un
  `overflow-x-auto`: sin él, en un móvil la tabla ensancha el `body` y toda la interfaz se
  desplaza en horizontal.
- **`course_id` basta como clave de fila DENTRO de un semestre**, y no hace falta un
  identificador de la fila del expediente: el `UNIQUE (student_id, course_id, academic_period)`
  impide que una materia salga dos veces en el mismo período. Repetida en otro semestre es otra
  fila en otra tabla, que es exactamente como debe verse.
- **El acumulado no se anuncia cuando no hay semestres cerrados.** «Promedio acumulado 0.00» en
  la primera pantalla de quien acaba de ingresar se lee como una nota, no como un vacío.
- **La cabecera dice «créditos aprobados EN TOTAL».** Cada semestre anuncia también los suyos, y
  sin esa palabra las dos cifras se leen como la misma.
- **El expediente se consulta todo el año**, dentro y fuera de la ventana de matrícula, y se
  considera fresco cinco minutos: solo lo mueve el cierre de un período, que ocurre una vez por
  semestre. Refrescarlo al volver a la pestaña gastaría una petición para traer lo mismo. Es la
  política CONTRARIA a la de los cupos, y por la misma razón: cada consulta se refresca según
  cada cuánto cambia de verdad lo que devuelve.
- **Los accesos de la pantalla de inicio siguen el MISMO orden que la barra de navegación**, y
  eso obliga a tocar los dos sitios a la vez. Al añadir «Expediente» al menú y no a `HomePage`,
  el test de la pantalla de inicio falló: está escrito contra la lista completa y en orden
  justamente para que las dos no puedan divergir en silencio.

**EL CICLO ESTÁ CERRADO.** `POST /admin/enrollment-periods/{id}/close` convierte las notas del
período en `academic_history`, y `tests/integration/test_academic_cycle.py` lo demuestra de punta
a punta: matricular Cálculo I → calificar → cerrar → y solo entonces poder matricular Cálculo II,
que la exige como prerrequisito. Esa prueba absorbe lo que iba a ser la 9.5: era el sitio natural
para escribirla, porque es la única que demuestra que el sistema funciona más de un semestre.

De la 9.3, lo que no se vuelve a discutir:

- **Es la única operación IRREVERSIBLE del sistema**, así que TODO se comprueba antes de escribir
  nada, y los cuatro rechazos van separados porque llevan a acciones distintas: no hacer nada,
  esperar a que cierre la ventana, perseguir notas concretas, o revisar un choque a mano.
- **`consolidated_at` es una FECHA y no un booleano.** Lo primero que se pregunta cuando alguien
  reclama una nota es si el cierre fue antes o después de que la corrigieran, y eso no se
  reconstruye a posteriori.
- **`CHECK (consolidated_at IS NULL OR is_active = false)`.** Un período consolidado y activo
  permitiría matricularse en un semestre cuyo expediente ya se escribió, y esas matrículas no
  llegarían nunca al historial. El estado prohibido es INVISIBLE —nada falla, unas matrículas se
  pierden en silencio— y por eso lo sostiene la base.
- **El `status` se deriva de la nota**, no se recibe. Si quien construye el registro pudiera
  decidirlo, un 4.2 podría acabar figurando como perdido.
- **El expediente guarda la materia, no el grupo.** Años después, a quien lee un historial le da
  igual con qué docente se vio Cálculo I.

De la 9.2, lo que no se vuelve a discutir:

- **La nota vive en `enrollments.final_grade`, no en `academic_history`.** El historial es un
  registro consolidado —decide prerrequisitos y aparece en el expediente— y escribir cada tecleo
  del docente allí haría irreversible una corrección tan normal como equivocarse de fila. La nota
  nace como BORRADOR y la 9.3 la consolida en una sola operación transaccional.
- **`Grade` es un value object con `Decimal`, no un `float`.** `0.1 + 0.2` no es `0.3` en coma
  flotante, y una nota en la frontera de aprobación decidiría el semestre de alguien según un
  error de redondeo binario. El redondeo es HALF_UP y no el bancario de Python: `2.995` sube a
  `3.00` y aprueba.
- **`CHECK (final_grade IS NULL) = (graded_at IS NULL)`**: la nota y su instante van juntas o no
  van. Sin eso, un `UPDATE` a mano dejaría una nota sin fecha —y la 9.3 no sabría si se
  calificó— o una fecha sin nota, que no significa nada.
- **Cinco rechazos separados** al calificar (`OFFERING_NOT_FOUND`, `OFFERING_NOT_ASSIGNED`,
  `GRADING_PERIOD_CLOSED`, `STUDENT_NOT_ENROLLED`, `ENROLLMENT_CANCELLED_CANNOT_GRADE`) porque se
  corrigen en cinco sitios distintos. `_AccesoAlGrupo` es una pieza compartida entre las dos
  operaciones para que la comprobación no pueda separarse: es el tipo de código que se corrige
  en un sitio y se olvida en el otro, dejando un endpoint abierto sin que nada falle.

**Dos bugs que la 9.2 destapó y conviene no repetir:**

El catálogo se pedía SIN `program_id` mientras el perfil del estudiante no había llegado, y esa
consulta devuelve el catálogo entero: durante ese instante alguien de Derecho veía Programación
II, que es exactamente lo que la iteración 6.1 vino a impedir. La guarda `listoParaConsultar`
estaba escrita en `CatalogPage` y **nunca se cableó** —era una variable calculada que no usaba
nadie—; ahora se pasa como `enabled` a `useCourses`. Lo destapó un test que fallaba de forma
intermitente en CI, y que se leía como flaky cuando era un fallo real que dependía de qué
respuesta llegara primero. Hay un test que lo fija: comprueba que NINGUNA consulta del catálogo
sale sin `program_id`.

El segundo: un `<input type="number" step="0.01">` bloquea
el envío del formulario EN SILENCIO —sin error ni mensaje— para valores como `3.5`, porque la
validación nativa comprueba el paso con aritmética de coma flotante y `3.5 / 0.01` no da un
entero exacto. Se usa `step="any"`; el rango sigue en `min`/`max`, en `Grade` y en el `CHECK`.

**EL HALLAZGO QUE DETERMINA LA FASE 9: `academic_history` solo la escribe el seed.** Ningún caso
de uso la crea. Con esa tabla vacía en producción, `find_approved_course_ids` devuelve vacío,
NADIE cumple ningún prerrequisito y la matrícula se bloquea entera a partir del segundo
semestre; el semáforo se calcula mal y `approved_credits` queda siempre en 0. El sistema, hoy,
**solo funciona el primer semestre de su vida**. El ciclo `inscribir → cursar → calificar →
consolidar → prerrequisito` tiene la primera y la última pieza; la Fase 9 pone las tres del
medio.

De la 9.1, lo que no es obvio:

- **`professors.user_id` es NULLABLE y la clave foránea es `ON DELETE SET NULL`.** Un docente
  existe como dato del catálogo antes de tener cuenta —los diez del seed nacieron así— y sigue
  existiendo después de que la cuenta se borre: `course_offerings.professor_id` lo apunta, y con
  `CASCADE` desaparecería el docente de grupos que ya se dictaron. Se pierde el acceso, no la
  historia. El índice único es PARCIAL (`WHERE user_id IS NOT NULL`) porque los `NULL` son la
  mayoría y no deben competir entre sí.
- **Un ADMIN no puede entrar por `/professors`.** Va contra el reflejo de que «admin puede
  todo» y es deliberado: quien conoce la nota es quien dictó la clase, y dejar que la ponga
  cualquiera con permiso amplio borra esa responsabilidad, que la 9.2 necesita clara.
- **`PROFESSOR_REQUIRED` (403) y `PROFESSOR_PROFILE_NOT_FOUND` (404) están separados** porque se
  corrigen en sitios distintos: uno cambiando el rol, otro dando de alta al docente.
- **La navegación pasó a filtrar por ROL y no por «hay sesión».** El rol nuevo destapó el fallo:
  un docente tiene sesión y no tiene plan ni materias propias, así que esos enlaces le llevaban
  a pantallas que responden `STUDENT_PROFILE_NOT_FOUND`. `RequireAdmin` y `RequireProfessor` son
  ahora envoltorios de `RequireRole`.
- **`test_professor_authorization.py` recorre TODAS las rutas `/professors`** y exige el guard,
  igual que su gemelo de admin. Es el que seguirá protegiendo cuando la 9.2 añada las notas.

**Fase 8 — Interfaz de administración: COMPLETA.** 8.1 estructura, acceso y panel ✅
(`ca86677`) · 8.2 períodos, materias y grupos ✅ (`aed5063`) · 8.3 planes, espacios y requisitos
✅ (fase A `15c5e80`, fase B `d2d6d9e`) · 8.4 reportes visuales y CSV ✅ (esta iteración).

De la 8.4, tres decisiones que no se vuelven a discutir:

- **El CSV se arma en el cliente**, con los datos que ya están en pantalla. Los reportes se
  calculan EN VIVO en cada llamada, así que pedir un CSV al servidor devolvería cifras distintas
  de las que quien exporta está mirando. Un archivo que no cuadra con su pantalla es peor que no
  tener exportación.
- **Sin librería de gráficas.** El gráfico de barras son `div` con anchos en porcentaje
  (`components/ui/BarChart.tsx`). Una dependencia de ese tamaño pesa más que la pantalla entera
  que la usaría, y este es el único gráfico del producto. Las barras van `aria-hidden` y **la
  tabla de al lado es la fuente de la verdad**: una barra no se puede leer con un lector de
  pantalla ni copiar a un informe.
- **`lib/csv.ts` neutraliza fórmulas.** Los nombres de materias y programas los escribe quien
  administra; uno que empiece por `=`, `+`, `-` o `@` lo ejecuta Excel al abrir el archivo. Se
  les antepone un apóstrofo. También lleva BOM y separador `;`, que es lo que Excel espera con la
  configuración regional de Colombia: con comas, todas las columnas se apilan en una sola y
  parece que la exportación está rota.

La 8.3 se partió en dos a propósito. La **fase A** cubrió lo que no dependía de la decisión sobre
retroactividad: seis endpoints (`POST`/`GET /admin/spaces`, `GET /admin/programs`,
`GET`/`PUT`/`DELETE` del plan) y sus pantallas `/admin/planes` y `/admin/espacios`. La **fase B**
tomó la decisión y añadió el editor de requisitos: `PUT`/`DELETE` sobre
`.../plan/{course_id}/requirements/{required_course_id}`.

Tres rechazos son el valor real de la iteración:

- **Quitar una materia del plan es destructivo sin parecerlo.** La clave foránea de
  `program_course_requirements` apunta al plan con `ON DELETE CASCADE`: sacar `MAT101` borraría
  en silencio el requisito «`MAT102` exige `MAT101`» y la base no daría error. `DELETE` lo
  rechaza con `COURSE_REQUIRED_BY_OTHERS` **nombrando quién depende**, porque «no se pudo»
  dejaría a quien administra sin saber qué corregir.
- **El código del aula se normaliza ANTES de comprobar el duplicado.** Sin eso, `a-201` y
  `A-201` serían dos filas para el mismo salón, y con dos filas la restricción de doble reserva
  de la 7.2 no impide nada: cree que son sitios distintos. Es el problema que la 7.1 vino a
  resolver, volviendo por la puerta de atrás.

- **Un ciclo de requisitos con un prerrequisito dentro es insatisfacible, y nada avisaba.** La
  base acepta cada fila por separado, el validador las rechaza una a una sin poder decir por qué
  y el semáforo las pinta bloqueadas sin salida; el error aparecía meses después, con un
  estudiante atascado. `RequirementGraph` recorre el grafo del plan y rechaza con la vuelta
  completa en `details.cycle`. Un ciclo de PUROS correquisitos sí es legítimo: es el bloque que
  se cursa junto, y la 6.2 construyó la exención de pares mutuos para poder inscribirlo.

La 8.3 también consumió `GET /admin/spaces/available`, que la 7.3 dejó sin interfaz; retiró
`obtenerGrupo` del cliente del catálogo, que no llamaba nadie; y dio schema propio al plan de
administración, que reutilizaba el del estudiante y por eso mandaba `status: "NOT_OFFERED"` en
todas las materias —un dato que se lee como un hecho sobre la oferta cuando solo significaba
«no se calculó»—.

**Nota de la suite de frontend: DOS PLAZOS, y el orden entre ellos importa.**
`src/test/setup.ts` sube el `asyncUtilTimeout` de Testing Library a 5 s —el defecto de 1 s se
agotaba con los ficheros en paralelo en una máquina cargada— y `vite.config.ts` sube el
`testTimeout` de vitest a 15 s. Con los dos en 5 s, un `findBy*` lento agotaba el del TEST antes
que el suyo, y el resultado era un «Test timed out» que no dice qué elemento faltaba: el peor
mensaje posible para depurar, y el que hizo perder tiempo persiguiendo una falsa contención. Con
15 s arriba, un test roto sigue fallando a los 5 s con el error útil. No esconde nada: lo que
estaba escondiendo era el mensaje.

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
Aprovisionar Azure sigue pendiente (ver `deploy/azure/README.md`).

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

- **DECISIÓN TOMADA en la 8.3 fase B: los requisitos son RETROACTIVOS. No se versiona el plan
  de estudios.** No se vuelve a discutir; lo que sigue es por qué, porque la razón importa más
  que la respuesta.

  La determinaron tres hechos del código, no una preferencia:

  1. **Los dos tipos de requisito no se comportan igual.** Los prerrequisitos se validan SOLO
     al inscribir (`enroll_student.py`); creada la inscripción, nadie vuelve a comprobarlos.
     Añadir un prerrequisito retroactivamente no puede romper ninguna matrícula: no hay
     víctima. Los correquisitos sí se recalculan en cada lectura
     (`list_student_enrollments.py`) y en la cancelación (6.2.1). El problema no era «los
     requisitos»: era **añadir un correquisito**.
  2. **El radio de daño ya está acotado.** `list_student_enrollments` solo mira el período
     ACTIVO. Los períodos pasados no se releen nunca —de ellos queda el historial de
     aprobadas, contra el que los requisitos no se recalculan—. El alcance de un cambio
     retroactivo son las inscripciones activas del período activo, y nada más.
  3. **Versionar resolvería otro problema.** El *grandfathering* académico protege QUÉ
     MATERIAS hacen falta para graduarse —`program_courses`, a lo largo de cinco años—. La
     fase B edita reglas de SECUENCIA pedagógica, que se aplican desde la siguiente
     inscripción. El coste habría sido arrastrar una coordenada temporal por la clave foránea
     compuesta, los cuatro casos de uso que leen requisitos, el semáforo, la cancelación y el
     seed.

  **El aviso a la fase 10 tampoco hacía falta.** El estudiante ya ve el correquisito pendiente
  en `/mis-inscripciones` (`MyEnrollmentsPage.tsx`), y llega solo. Lo que sí faltaba, y la
  pregunta original no veía, es que hay un caso donde queda ATRAPADO SIN REMEDIO: con la
  ventana cerrada ve que le falta algo y no puede inscribir nada. Con la ventana abierta se lo
  arregla él. Por eso el caso de uso rechaza añadir un correquisito que afecte a inscripciones
  activas cuando la ventana NO está abierta, y lo permite cuando sí lo está.

- **Rate limiting.** `API.md` fija límites por endpoint (login 5/min por IP, inscripción 30/min,
  catálogo 120/min, admin 60/min) y no hay nada implementado. Con varias instancias detrás del
  Application Gateway, un contador en memoria no sirve: o el WAF de Application Gateway con reglas por IP, o un contador en Redis para
  los límites por usuario.
- **Autenticación propia frente a Microsoft Entra External ID.** El documento del proyecto nombra Microsoft Entra External ID; el código
  emite y valida sus propios JWT con bcrypt. `AuthService` es un puerto, así que cambiarlo sería
  escribir un adaptador nuevo y tocar `di.py`, sin rozar el dominio. Decisión pendiente.
- **`GET /enrollment-periods` público.** `API.md` sección 5 lo documenta como listado paginado
  de períodos; el único listado que existe es `GET /admin/enrollment-periods`, que exige rol
  ADMIN.
- **El seed no comparte ninguna materia entre programas.** El esquema sí lo admite
  (`program_courses` tiene clave primaria compuesta), pero los datos de ejemplo dan a cada
  programa materias propias, así que ese camino no se ejercita nunca. La fixture `catalogo`
  de los tests de integración SÍ lo hace desde la 6.2 —dos planes que comparten MAT101 y
  MAT102 con reglas distintas—, que es donde se comprueba que los requisitos dependen del
  plan.
- **El rol `PROFESSOR` no tiene todavía pantalla de administración.** Se enlaza una cuenta a un
  docente por el seed o a mano; no hay endpoint que lo haga.
- ~~El seed no crea inscripciones~~ **RESUELTO en la 9.3.** `_sembrar_inscripciones` crea filas
  reales que cuadran con `enrolled_count`, solo entre estudiantes del programa al que pertenece
  la materia, y **deja la mitad sin calificar a propósito** para que el rechazo del cierre se
  pueda probar a mano. Al escribirlo apareció un fallo que llevaba ahí desde siempre: el seed
  inscribía a la misma persona en los DOS grupos de una materia —dato que el propio sistema
  rechaza al inscribir— y al consolidar reventaba el `UNIQUE` del historial. De ahí salió también
  la comprobación de duplicados DENTRO del lote en `ConsolidatePeriodUseCase`, que antes solo
  miraba contra el historial existente.

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
│                   (admin · auth · catalog · enrollment · health · home · teaching · transcript)
├── lib/            cliente HTTP, errores de la API y configuración de TanStack Query
└── test/           MSW y el render con proveedores
```

El CI del frontend (`frontend-ci` en `ci.yml`) se activa solo porque existe
`frontend/package.json`, y ejecuta `lint`, `type-check`, `test` y `build`. Si se renombra
alguno de esos scripts, el job falla.

**Las acciones se fijan por versión MAYOR y estan en la que corre sobre Node 24**
(`checkout@v5`, `setup-python@v6`, `setup-node@v5`, `gitleaks-action@v3`). GitHub retira Node 20
de los runners en septiembre de 2026; hasta entonces avisa en cada corrida. Los bloques de Azure y
Docker que siguen COMENTADOS a la espera de aprovisionar la nube conservan versiones antiguas
—`azure-actions/*`, `docker/*`— y hay que revisarlas al descomentarlas, porque nadie las ha
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
