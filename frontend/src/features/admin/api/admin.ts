/**
 * Llamadas a los endpoints de administración.
 *
 * Todos exigen token con rol ADMIN: el backend lo declara una sola vez en el router, no
 * endpoint por endpoint. Aquí no se comprueba nada de eso —comprobarlo en el cliente sería
 * duplicar una regla que no protege nada—, solo se envía el token.
 */

import type {
  AvailableSpaces,
  EnrollmentPeriod,
  EnrollmentReport,
  NewCourse,
  NewEnrollmentPeriod,
  NewOffering,
  OccupancyReport,
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
