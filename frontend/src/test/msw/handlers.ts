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

/** Estado del servicio con el que responde el backend cuando todo va bien. */
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
}[] = [];

export function resetearInscripciones() {
  inscripcionesDePrueba.length = 0;
}

/** Añade una inscripción ya existente, para los tests que arrancan con materias inscritas. */
export function sembrarInscripcion(offeringId = "g1") {
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
  });
}

/**
 * Plan de estudios de prueba.
 *
 * Solo Cálculo I y Cálculo II pertenecen al programa del estudiante. Física queda FUERA a
 * propósito: es la materia con la que se comprueba que el catálogo ya no la ofrece por defecto
 * y que su ficha bloquea la inscripción.
 */
export const PLAN_DE_ESTUDIOS = {
  program_code: "ISIS",
  program_name: "Ingeniería de Sistemas",
  total_semesters: 10,
  // Se derivan de `MATERIAS` en vez de escribirse a mano: así el plan y el catálogo no
  // pueden divergir si alguien cambia un código o unos créditos.
  courses: MATERIAS.filter((m) => m.id === "c1" || m.id === "c2").map((m, indice) => ({
    ...m,
    suggested_semester: indice + 1,
    is_mandatory: true,
  })),
  total_credits: 8,
};

/** Identificadores de las materias del plan, para filtrar como lo hace el backend. */
const IDS_DEL_PLAN = new Set(PLAN_DE_ESTUDIOS.courses.map((c) => c.id));

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

  http.post(`${API_URL}/api/v1/auth/refresh`, () => HttpResponse.json(parDeTokens("renovado"))),

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

  http.get(`${API_URL}/api/v1/courses/:courseId`, ({ params }) => {
    const materia = MATERIAS.find((m) => m.id === params.courseId);

    if (!materia) {
      return respuestaDeError(404, "COURSE_NOT_FOUND", "La materia solicitada no existe");
    }

    // Cálculo II exige Cálculo I; el resto no tiene prerrequisitos.
    const prerequisites = materia.id === "c2" ? [MATERIAS[0]] : [];

    return HttpResponse.json({ ...materia, prerequisites });
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

    inscripcionesDePrueba.splice(indice, 1);

    return new HttpResponse(null, { status: 204 });
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
