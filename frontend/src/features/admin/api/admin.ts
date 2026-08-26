/**
 * Llamadas a los endpoints de administración.
 *
 * Todos exigen token con rol ADMIN: el backend lo declara una sola vez en el router, no
 * endpoint por endpoint. Aquí no se comprueba nada de eso —comprobarlo en el cliente sería
 * duplicar una regla que no protege nada—, solo se envía el token.
 */

import type {
  AvailableSpace,
  AvailableSpaces,
  EnrollmentPeriod,
  EnrollmentReport,
  NewCourse,
  NewEnrollmentPeriod,
  NewOffering,
  NewSpace,
  OccupancyReport,
  Program,
  ProgramPlan,
} from "@/features/admin/api/types";
import type { Course, Offering } from "@/features/catalog/api/types";
import { api } from "@/lib/api/client";

/** Cifras de matrícula del período activo, calculadas en vivo. */
export function obtenerReporteDeInscripciones(token: string, signal?: AbortSignal) {
  return api.get<EnrollmentReport>("/api/v1/admin/reports/enrollments", { token, signal });
}

/**
 * Ocupación de los grupos, del más lleno al más vacío.
 *
 * `size` pequeño a propósito en el panel: lo que hay que vigilar son los que están a punto de
 * llenarse, y esos son los primeros. Traer trescientos grupos para mostrar cinco sería mover
 * datos que nadie mira.
 */
export function obtenerReporteDeOcupacion(
  token: string,
  { size = 5 }: { size?: number } = {},
  signal?: AbortSignal,
) {
  return api.get<OccupancyReport>("/api/v1/admin/reports/occupancy", {
    query: { page: 1, size },
    token,
    signal,
  });
}

/** Claves de caché de administración, en un solo sitio como en el resto de la aplicación. */
export const clavesAdmin = {
  todo: ["admin"] as const,
  periodos: ["admin", "periodos"] as const,
  programas: ["admin", "programas"] as const,
  plan: (programId: string) => ["admin", "plan", programId] as const,
  espacios: (filtros: object) => ["admin", "espacios", filtros] as const,
  disponibilidad: (c: object) => ["admin", "disponibilidad", c] as const,
  inscripciones: ["admin", "reporte-inscripciones"] as const,
  ocupacion: (size: number) => ["admin", "reporte-ocupacion", size] as const,
};

/** Ventanas de matrícula, de la más reciente a la más antigua. */
export function listarPeriodos(token: string, signal?: AbortSignal) {
  return api.get<{ items: EnrollmentPeriod[]; total: number }>(
    "/api/v1/admin/enrollment-periods",
    { query: { page: 1, size: 50 }, token, signal },
  );
}

/** Abre una ventana de matrícula. Nace INACTIVA: activarla es una decisión aparte. */
export function crearPeriodo(payload: NewEnrollmentPeriod, token: string) {
  return api.post<EnrollmentPeriod>("/api/v1/admin/enrollment-periods", { body: payload, token });
}

/**
 * Activa una ventana y cierra la que estuviera abierta.
 *
 * Es la operación más delicada de administración: cambia lo que ven todos los estudiantes a la
 * vez. El índice único parcial de PostgreSQL garantiza que nunca haya dos activas.
 */
export function activarPeriodo(periodId: string, token: string) {
  return api.put<EnrollmentPeriod>(
    `/api/v1/admin/enrollment-periods/${periodId}/activate`,
    { token },
  );
}

/** Crea una materia del catálogo. */
export function crearMateria(payload: NewCourse, token: string) {
  return api.post<Course>("/api/v1/admin/courses", { body: payload, token });
}

/** Abre un grupo de una materia en el período activo. */
export function crearGrupo(payload: NewOffering, token: string) {
  return api.post<Offering>("/api/v1/admin/offerings", { body: payload, token });
}

/**
 * Ajusta el cupo total de un grupo.
 *
 * No lleva `version`: el bloqueo optimista lo resuelve el servidor, que relee y reintenta. Si
 * aun así pierde la carrera responde `CONCURRENT_MODIFICATION`, y entonces lo correcto es
 * releer y volver a decidir, no reintentar a ciegas con el mismo número.
 */
export function ajustarCupo(offeringId: string, totalCapacity: number, token: string) {
  return api.put<Offering>(`/api/v1/admin/offerings/${offeringId}/capacity`, {
    body: { total_capacity: totalCapacity },
    token,
  });
}

/** Espacios libres en una franja del período activo. */
export function consultarDisponibilidad(
  consulta: { day_of_week: number; start_time: string; end_time: string; min_capacity?: number },
  token: string,
  signal?: AbortSignal,
) {
  return api.get<AvailableSpaces>("/api/v1/admin/spaces/available", {
    query: consulta,
    token,
    signal,
  });
}

/** Programas académicos, para elegir cuál plan editar. */
export function listarProgramas(token: string, signal?: AbortSignal) {
  return api.get<{ items: Program[]; total: number }>("/api/v1/admin/programs", {
    token,
    signal,
  });
}

/**
 * Plan de estudios de un programa cualquiera.
 *
 * Es distinto de `GET /students/me/study-plan`, y no por capricho: allí el programa sale del
 * token y no puede elegirse. Aquí lo elige quien administra, que tiene que poder editar
 * cualquiera, y por eso vive tras el rol de administración.
 */
export function obtenerPlanDePrograma(programId: string, token: string, signal?: AbortSignal) {
  return api.get<ProgramPlan>(`/api/v1/admin/programs/${programId}/plan`, { token, signal });
}

/** Pone una materia en el plan, o cambia sus datos si ya estaba. Idempotente. */
export function ponerMateriaEnPlan(
  programId: string,
  courseId: string,
  datos: { suggested_semester: number; is_mandatory: boolean },
  token: string,
) {
  return api.put<void>(`/api/v1/admin/programs/${programId}/plan/${courseId}`, {
    body: datos,
    token,
  });
}

/** Saca una materia del plan. Se rechaza si otras del plan la exigen. */
export function quitarMateriaDelPlan(programId: string, courseId: string, token: string) {
  return api.delete<void>(`/api/v1/admin/programs/${programId}/plan/${courseId}`, { token });
}

/**
 * Deja un requisito cargado en el plan, o le cambia el tipo si ya estaba.
 *
 * `PUT` porque es idempotente: la clave del requisito es la terna `(programa, materia, exigida)`
 * y NO incluye el tipo, así que volver a mandarlo con otro tipo lo cambia en vez de duplicarlo.
 */
export function ponerRequisito(
  programId: string,
  courseId: string,
  requiredCourseId: string,
  requirementType: "PREREQUISITE" | "COREQUISITE",
  token: string,
) {
  return api.put<void>(
    `/api/v1/admin/programs/${programId}/plan/${courseId}/requirements/${requiredCourseId}`,
    { body: { requirement_type: requirementType }, token },
  );
}

/** Quita un requisito del plan. Nunca se rechaza: relajar una regla no deja a nadie incompleto. */
export function quitarRequisito(
  programId: string,
  courseId: string,
  requiredCourseId: string,
  token: string,
) {
  return api.delete<void>(
    `/api/v1/admin/programs/${programId}/plan/${courseId}/requirements/${requiredCourseId}`,
    { token },
  );
}

/** Da de alta un espacio físico. El código se guarda normalizado. */
export function crearEspacio(payload: NewSpace, token: string) {
  return api.post<AvailableSpace>("/api/v1/admin/spaces", { body: payload, token });
}

/** Inventario completo de espacios, con filtros opcionales. */
export function listarEspacios(
  filtros: { space_type?: string; campus?: string },
  token: string,
  signal?: AbortSignal,
) {
  return api.get<{ items: AvailableSpace[]; total: number }>("/api/v1/admin/spaces", {
    query: filtros,
    token,
    signal,
  });
}
