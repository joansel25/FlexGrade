/**
 * Respuestas simuladas de la API para los tests.
 *
 * Se usa MSW (Mock Service Worker), que intercepta a nivel de red en vez de sustituir `fetch`
 * con un doble. La diferencia importa: con MSW se prueba el cliente HTTP de verdad —cabeceras,
 * códigos de estado, interpretación del cuerpo de error— y no una versión falsa de él que
 * siempre se comporta bien.
 */

import { HttpResponse, http } from "msw";

/** Base que usan los tests; coincide con la de `.env.example`. */
export const API_URL = "http://localhost:8000";

/**
 * Estado del servicio con el que responde el backend cuando todo va bien.
 *
 * Ninguna pantalla lo consume desde la iteración 6.4, que retiró el indicador de estado de la
 * interfaz del estudiante. Se conserva porque `client.test.ts` usa `/health` como el GET
 * correcto más simple que existe para probar el cliente HTTP: es un endpoint real, sin token
 * ni parámetros, y sustituirlo por uno inventado haría que el test dejara de parecerse a una
 * petición de verdad.
 */
export const ESTADO_SANO = {
  status: "ok",
  environment: "test",
  version: "0.1.0",
};

/** Cuenta con la que se autentican los tests. */
export const USUARIO = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "estudiante@tdea.edu.co",
  role: "STUDENT" as const,
};

/** Perfil que devuelve `GET /students/me`. */
export const PERFIL = {
  id: "22222222-2222-2222-2222-222222222222",
  student_code: "1234567",
  full_name: "Joan Sebastián Cárdenas",
  email: USUARIO.email,
  program: {
    id: "33333333-3333-3333-3333-333333333333",
    code: "ISIS",
    name: "Ingeniería de Sistemas",
  },
  current_semester: 6,
  enrollment_date: "2022-01-15",
};

export const CREDENCIALES_VALIDAS = { email: USUARIO.email, password: "SecurePass123" };

/** Par de tokens con la forma que promete `API.md`. */
export function parDeTokens(sufijo = "1") {
  return {
    access_token: `access-${sufijo}`,
    refresh_token: `refresh-${sufijo}`,
    token_type: "bearer",
    expires_in: 3600,
  };
}

/** Catálogo de prueba: tres materias, una de ellas con prerrequisito. */
export const MATERIAS = [
  {
    id: "c1",
    code: "MAT101",
    name: "Cálculo I",
    credits: 4,
    description: "Fundamentos de cálculo diferencial",
  },
  { id: "c2", code: "MAT102", name: "Cálculo II", credits: 4, description: "Cálculo integral" },
  { id: "c3", code: "FIS101", name: "Física", credits: 3, description: null },
  // El taller es el correquisito de Cálculo II: existe para que la ficha tenga qué pintar en
  // esa sección, que es la que estrena la iteración 6.2.
  {
    id: "c4",
    code: "TAL101",
    name: "Taller de Cálculo I",
    credits: 1,
    description: "Prácticas dirigidas",
  },
];

/** Grupos de Cálculo I: uno con holgura, otro a punto de llenarse y otro lleno. */
export const GRUPOS = {
  course_id: "c1",
  course_code: "MAT101",
  period_code: "2025-2-V1",
  offerings: [
    {
      id: "g1",
      group_number: "01",
      professor: "Ana Pérez",
      total_capacity: 40,
      enrolled_count: 10,
      available_slots: 30,
      schedule: [
        { day_of_week: 1, start_time: "08:00:00", end_time: "10:00:00", classroom: "A-201" },
      ],
    },
    {
      id: "g2",
      group_number: "02",
      professor: null,
      total_capacity: 30,
      enrolled_count: 28,
      available_slots: 2,
      schedule: [],
    },
    {
      id: "g3",
      group_number: "03",
      professor: "Luis Gómez",
      total_capacity: 25,
      enrolled_count: 25,
      available_slots: 0,
      schedule: [
        { day_of_week: 3, start_time: "14:00:00", end_time: "16:00:00", classroom: "B-101" },
      ],
    },
  ],
};

/** Período de matrícula abierto. */
export const PERIODO_ABIERTO = {
  id: "p1",
  code: "2025-2-V1",
  academic_period: "2025-2",
  name: "Matrícula 2025-2 primera vuelta",
  starts_at: "2025-11-15T08:00:00Z",
  ends_at: "2025-11-17T18:00:00Z",
  is_active: true,
  is_open: true,
  time_remaining_seconds: 172_800,
};

/**
 * Inscripciones del estudiante en los tests.
 *
 * Es un array mutable a propósito: inscribir y cancelar lo modifican, así que los tests pueden
 * comprobar el recorrido completo —inscribo, aparece en mis materias, cancelo, desaparece— en
 * vez de solo la llamada aislada. `resetearInscripciones` lo devuelve a cero entre casos.
 */
export const inscripcionesDePrueba: {
  id: string;
  course_offering_id: string;
  course_id: string;
  course_code: string;
  course_name: string;
  credits: number;
  group_number: string;
  professor: string | null;
  schedule: { day_of_week: number; start_time: string; end_time: string; classroom: string | null }[];
  enrolled_at: string | null;
  pending_corequisites: string[];
}[] = [];

export function resetearInscripciones() {
  inscripcionesDePrueba.length = 0;
}

/**
 * Añade una inscripción ya existente, para los tests que arrancan con materias inscritas.
 *
 * `pendientes` reproduce los correquisitos que el backend calcula y devuelve por materia. Se
 * declara aquí y no se deduce porque el doble no tiene planes de estudio: lo que se prueba en
 * el frontend es que la pantalla los muestre, no que se calculen bien —eso vive en el backend,
 * que es donde se decide si la inscripción se acepta—.
 */
export function sembrarInscripcion(offeringId = "g1", pendientes: string[] = []) {
  const grupo = GRUPOS.offerings.find((o) => o.id === offeringId) ?? GRUPOS.offerings[0]!;

  inscripcionesDePrueba.push({
    id: `e-${grupo.id}`,
    course_offering_id: grupo.id,
    course_id: "c1",
    course_code: "MAT101",
    course_name: "Cálculo I",
    credits: 4,
    group_number: grupo.group_number,
    professor: grupo.professor,
    schedule: grupo.schedule,
    enrolled_at: "2025-11-15T14:30:00Z",
    pending_corequisites: pendientes,
  });
}

/**
 * Plan de estudios de prueba.
 *
 * Contiene todo el catálogo MENOS Física, que queda fuera a propósito: es la materia con la que
 * se comprueba que el catálogo ya no la ofrece por defecto y que su ficha bloquea la
 * inscripción.
 */
/** Estado de cada materia en el plan de prueba, con un caso de cada tipo. */
const SEMAFORO_DE_PRUEBA: Record<
  string,
  {
    status: string;
    missing_prerequisites: string[];
    missing_corequisites: string[];
    corequisites: string[];
  }
> = {
  c1: {
    status: "APPROVED",
    missing_prerequisites: [],
    missing_corequisites: [],
    corequisites: [],
  },
  c2: {
    status: "BLOCKED",
    missing_prerequisites: ["MAT101"],
    missing_corequisites: [],
    corequisites: ["TAL101"],
  },
  c4: {
    status: "AVAILABLE",
    missing_prerequisites: [],
    missing_corequisites: [],
    corequisites: [],
  },
};

export const PLAN_DE_ESTUDIOS = {
  program_id: "p1",
  program_code: "ISIS",
  program_name: "Ingeniería de Sistemas",
  total_semesters: 10,
  // Se derivan de `MATERIAS` en vez de escribirse a mano: así el plan y el catálogo no
  // pueden divergir si alguien cambia un código o unos créditos.
  courses: MATERIAS.filter((m) => m.id !== "c3").map((m, indice) => ({
    ...m,
    suggested_semester: indice + 1,
    is_mandatory: true,
    // El semáforo lo calcula el servidor, así que el doble se limita a declararlo. Los tres
    // estados que aquí importan son los que cambian lo que la pantalla deja hacer: uno
    // pulsable, uno terminado y uno bloqueado con su motivo.
    ...SEMAFORO_DE_PRUEBA[m.id],
  })),
  total_credits: 9,
  approved_credits: 4,
};

/** Identificadores de las materias del plan, para filtrar como lo hace el backend. */
const IDS_DEL_PLAN = new Set(PLAN_DE_ESTUDIOS.courses.map((c) => c.id));

/** Cifras del panel de administración. */
export const REPORTE_INSCRIPCIONES = {
  period_code: "2025-2-V1",
  generated_at: "2025-11-16T09:00:00Z",
  totals: { total_enrollments: 412, unique_students: 173, active_offerings: 19 },
  by_program: [
    { program_code: "ISIS", program_name: "Ingeniería de Sistemas", enrollments: 240, students: 98 },
  ],
};

/**
 * Ocupación, del grupo más lleno al más vacío.
 *
 * El primero está por encima del umbral crítico y el segundo por debajo: es lo que permite
 * comprobar que la pantalla los distingue en vez de pintarlos todos igual.
 */
export const REPORTE_OCUPACION = {
  period_code: "2025-2-V1",
  generated_at: "2025-11-16T09:00:00Z",
  offerings: [
    {
      offering_id: "g1",
      course_code: "MAT101",
      course_name: "Cálculo I",
      group_number: "01",
      total_capacity: 40,
      enrolled_count: 39,
      available_slots: 1,
      occupancy_rate: 97.5,
    },
    {
      offering_id: "g2",
      course_code: "MAT102",
      course_name: "Cálculo II",
      group_number: "01",
      total_capacity: 40,
      enrolled_count: 20,
      available_slots: 20,
      occupancy_rate: 50.0,
    },
  ],
  total: 2,
  page: 1,
  size: 5,
};

/** Una ventana de matrícula inactiva, base de las que se crean en los tests. */
const PERIODO_INACTIVO = {
  id: "p-2026",
  code: "2026-1-V1",
  academic_period: "2026-1",
  name: "Matrícula 2026-1",
  starts_at: "2026-01-10T13:00:00Z",
  ends_at: "2026-01-20T23:00:00Z",
  is_active: false,
};

/**
 * Ventanas de matrícula de los tests.
 *
 * Array mutable, como `inscripcionesDePrueba`: crear y activar lo modifican, así que los tests
 * pueden comprobar el recorrido completo en vez de solo la llamada aislada.
 */
export const periodosDePrueba: (typeof PERIODO_INACTIVO)[] = [];

export function resetearPeriodos() {
  periodosDePrueba.length = 0;
  periodosDePrueba.push(
    { ...PERIODO_ABIERTO, academic_period: "2025-2", is_active: true },
    { ...PERIODO_INACTIVO },
  );
}

// Se puebla al cargar el módulo y no solo desde el `afterEach` del setup: sin esto el PRIMER
// test de la suite correría con la lista vacía y fallaría por un motivo que no es el suyo.
resetearPeriodos();

export const handlers = [
  http.get(`${API_URL}/health`, () => HttpResponse.json(ESTADO_SANO)),

  http.post(`${API_URL}/api/v1/auth/login`, async ({ request }) => {
    const cuerpo = (await request.json()) as { email: string; password: string };

    if (
      cuerpo.email !== CREDENCIALES_VALIDAS.email ||
      cuerpo.password !== CREDENCIALES_VALIDAS.password
    ) {
      return respuestaDeError(401, "INVALID_CREDENTIALS", "Correo o contraseña incorrectos");
    }

    return HttpResponse.json({ ...parDeTokens(), user: USUARIO });
  }),

  // El refresco devuelve la CUENTA además de los tokens desde la iteración 8.1: es la llamada
  // que restaura la sesión al recargar, y sin ese dato las rutas por rol no sabrían con qué rol.
  http.post(`${API_URL}/api/v1/auth/refresh`, () =>
    HttpResponse.json({ ...parDeTokens("renovado"), user: USUARIO }),
  ),

  http.get(`${API_URL}/api/v1/admin/enrollment-periods`, () =>
    HttpResponse.json({ items: periodosDePrueba, total: periodosDePrueba.length, page: 1, size: 50 }),
  ),

  http.post(`${API_URL}/api/v1/admin/enrollment-periods`, async ({ request }) => {
    const cuerpo = (await request.json()) as { code: string; name: string };

    if (periodosDePrueba.some((p) => p.code === cuerpo.code)) {
      return respuestaDeError(409, "DUPLICATE_PERIOD_CODE", "Ya existe ese código", {
        code: cuerpo.code,
      });
    }

    const creado = { ...PERIODO_INACTIVO, id: `p-${cuerpo.code}`, ...cuerpo, is_active: false };
    periodosDePrueba.push(creado);

    return HttpResponse.json(creado, { status: 201 });
  }),

  http.put(`${API_URL}/api/v1/admin/enrollment-periods/:id/activate`, ({ params }) => {
    // El índice único parcial de PostgreSQL garantiza que solo haya una activa; el doble
    // reproduce esa consecuencia porque es lo que la pantalla tiene que mostrar.
    for (const periodo of periodosDePrueba) {
      periodo.is_active = periodo.id === params.id;
    }

    return HttpResponse.json(periodosDePrueba.find((p) => p.id === params.id));
  }),

  http.post(`${API_URL}/api/v1/admin/courses`, async ({ request }) => {
    const cuerpo = (await request.json()) as { code: string; name: string; credits: number };

    if (MATERIAS.some((m) => m.code === cuerpo.code.toUpperCase())) {
      return respuestaDeError(409, "DUPLICATE_COURSE_CODE", "Ya existe esa materia", {
        code: cuerpo.code,
      });
    }

    return HttpResponse.json({ id: `c-${cuerpo.code}`, description: null, ...cuerpo }, { status: 201 });
  }),

  http.post(`${API_URL}/api/v1/admin/offerings`, () =>
    HttpResponse.json({ ...GRUPOS.offerings[0], group_number: "07" }, { status: 201 }),
  ),

  http.put(`${API_URL}/api/v1/admin/offerings/:id/capacity`, async ({ request }) => {
    const cuerpo = (await request.json()) as { total_capacity: number };

    // El grupo `g1` de la ocupación tiene 39 inscritos: bajar de ahí expulsaría gente.
    if (cuerpo.total_capacity < 39) {
      return respuestaDeError(409, "CAPACITY_BELOW_ENROLLED", "Hay más inscritos", {
        enrolled: 39,
        requested: cuerpo.total_capacity,
      });
    }

    return HttpResponse.json({ ...GRUPOS.offerings[0], total_capacity: cuerpo.total_capacity });
  }),

  http.get(`${API_URL}/api/v1/admin/reports/enrollments`, ({ request }) => {
    if (!request.headers.get("Authorization")?.startsWith("Bearer ")) {
      return respuestaDeError(401, "MISSING_TOKEN", "Falta el token de acceso");
    }

    return HttpResponse.json(REPORTE_INSCRIPCIONES);
  }),

  http.get(`${API_URL}/api/v1/admin/reports/occupancy`, ({ request }) => {
    if (!request.headers.get("Authorization")?.startsWith("Bearer ")) {
      return respuestaDeError(401, "MISSING_TOKEN", "Falta el token de acceso");
    }

    return HttpResponse.json(REPORTE_OCUPACION);
  }),

  http.post(`${API_URL}/api/v1/auth/logout`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API_URL}/api/v1/courses`, ({ request }) => {
    const url = new URL(request.url);
    const busqueda = url.searchParams.get("search")?.toLowerCase() ?? "";
    const semestre = url.searchParams.get("semester");

    let resultado = MATERIAS;

    // El backend acota por programa cuando se le pasa `program_id`; el doble hace lo mismo.
    if (url.searchParams.get("program_id")) {
      resultado = resultado.filter((m) => IDS_DEL_PLAN.has(m.id));
    }

    if (busqueda) {
      resultado = resultado.filter(
        (m) => m.name.toLowerCase().includes(busqueda) || m.code.toLowerCase().includes(busqueda),
      );
    }

    // El plan de estudios de prueba: solo Cálculo I está sugerido en el semestre 6.
    if (semestre === "6") {
      resultado = resultado.filter((m) => m.id === "c1");
    }

    return HttpResponse.json({
      items: resultado,
      total: resultado.length,
      page: Number(url.searchParams.get("page") ?? "1"),
      size: Number(url.searchParams.get("size") ?? "20"),
    });
  }),

  http.get(`${API_URL}/api/v1/courses/:courseId/offerings`, ({ params }) => {
    if (params.courseId !== "c1") {
      return HttpResponse.json({ ...GRUPOS, course_id: String(params.courseId), offerings: [] });
    }

    return HttpResponse.json(GRUPOS);
  }),

  http.get(`${API_URL}/api/v1/courses/:courseId`, ({ params, request }) => {
    const materia = MATERIAS.find((m) => m.id === params.courseId);

    if (!materia) {
      return respuestaDeError(404, "COURSE_NOT_FOUND", "La materia solicitada no existe");
    }

    // Los requisitos pertenecen a un plan de estudios: sin `program_id` el backend devuelve
    // las dos listas vacías, y el doble hace exactamente lo mismo. Reproducirlo importa
    // porque es lo que obliga a la interfaz a enviar el programa.
    const programId = new URL(request.url).searchParams.get("program_id");

    if (!programId) {
      return HttpResponse.json({
        ...materia,
        program_id: null,
        prerequisites: [],
        corequisites: [],
      });
    }

    // Cálculo II exige aprobar Cálculo I antes y cursar el taller a la vez.
    const prerequisites = materia.id === "c2" ? [MATERIAS[0]] : [];
    const corequisites = materia.id === "c2" ? [MATERIAS[3]] : [];

    return HttpResponse.json({ ...materia, program_id: programId, prerequisites, corequisites });
  }),

  http.get(`${API_URL}/api/v1/enrollment-periods/current`, () =>
    HttpResponse.json(PERIODO_ABIERTO),
  ),

  http.get(`${API_URL}/api/v1/students/me/enrollments`, () =>
    HttpResponse.json({
      period: "2025-2",
      period_code: "2025-2-V1",
      items: inscripcionesDePrueba,
      total_credits: inscripcionesDePrueba.reduce((suma, i) => suma + i.credits, 0),
    }),
  ),

  http.get(`${API_URL}/api/v1/students/me/study-plan`, () =>
    HttpResponse.json(PLAN_DE_ESTUDIOS),
  ),

  http.get(`${API_URL}/api/v1/students/me/receipt`, () =>
    // Un PDF mínimo pero con la firma real del formato: lo que se prueba es que la descarga
    // llega y se entrega al navegador, no que ReportLab dibuje bien —eso se comprueba en el
    // backend, que es donde se genera.
    HttpResponse.arrayBuffer(new TextEncoder().encode("%PDF-1.4 falso").buffer, {
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": 'attachment; filename="comprobante-matricula-1234567-2025-2-V1.pdf"',
      },
    }),
  ),

  http.get(`${API_URL}/api/v1/students/me/schedule`, () =>
    HttpResponse.json({
      period: "2025-2",
      blocks: inscripcionesDePrueba.flatMap((i) =>
        i.schedule.map((f) => ({
          course_code: i.course_code,
          course_name: i.course_name,
          group_number: i.group_number,
          professor: i.professor,
          day_of_week: f.day_of_week,
          start_time: f.start_time,
          end_time: f.end_time,
          classroom: f.classroom,
        })),
      ),
    }),
  ),

  http.post(`${API_URL}/api/v1/enrollments`, async ({ request }) => {
    const cuerpo = (await request.json()) as { course_offering_id: string };
    const grupo = GRUPOS.offerings.find((o) => o.id === cuerpo.course_offering_id);

    if (!grupo) {
      return respuestaDeError(404, "OFFERING_NOT_FOUND", "El grupo solicitado no existe");
    }

    if (grupo.available_slots <= 0) {
      return respuestaDeError(
        409,
        "COURSE_CAPACITY_EXCEEDED",
        "El grupo no tiene cupos disponibles",
        { offering_id: grupo.id, capacity: grupo.total_capacity, enrolled: grupo.enrolled_count },
      );
    }

    sembrarInscripcion(grupo.id);

    return HttpResponse.json(
      {
        id: `e-${grupo.id}`,
        student_id: USUARIO.id,
        course_offering_id: grupo.id,
        course_code: "MAT101",
        course_name: "Cálculo I",
        group_number: grupo.group_number,
        enrolled_at: "2025-11-15T14:30:00Z",
        status: "ENROLLED",
      },
      { status: 201 },
    );
  }),

  http.delete(`${API_URL}/api/v1/enrollments/:enrollmentId`, ({ params }) => {
    const indice = inscripcionesDePrueba.findIndex((i) => i.id === params.enrollmentId);

    if (indice === -1) {
      return respuestaDeError(404, "ENROLLMENT_NOT_FOUND", "La inscripción no existe");
    }

    // El backend responde 200 con lo que canceló, no 204: la operación puede arrastrar el
    // bloque de correquisitos mutuos. El doble devuelve una sola porque el arrastre se
    // reproduce en los tests que lo necesitan, sobreescribiendo este handler.
    const [cancelada] = inscripcionesDePrueba.splice(indice, 1);

    return HttpResponse.json({
      cancelled: [
        {
          id: cancelada!.id,
          course_offering_id: cancelada!.course_offering_id,
          course_code: cancelada!.course_code,
          course_name: cancelada!.course_name,
          group_number: cancelada!.group_number,
        },
      ],
    });
  }),

  http.get(`${API_URL}/api/v1/students/me`, ({ request }) => {
    // Se comprueba la cabecera de verdad: es lo que demuestra que el token viaja en cada
    // petición protegida, que es justo lo que esta iteración añade.
    if (!request.headers.get("Authorization")?.startsWith("Bearer ")) {
      return respuestaDeError(401, "MISSING_TOKEN", "Falta el token de acceso");
    }

    return HttpResponse.json(PERFIL);
  }),
];

/** Construye una respuesta de error con el formato universal de `API.md`. */
export function respuestaDeError(
  status: number,
  code: string,
  message: string,
  details?: Record<string, unknown>,
) {
  return HttpResponse.json({ error: { code, message, details: details ?? {} } }, { status });
}
