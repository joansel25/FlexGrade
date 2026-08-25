/**
 * Llamadas a los endpoints del catálogo académico.
 *
 * Los endpoints del catálogo son PÚBLICOS en el backend: no exigen token. Aun así el frontend
 * los muestra tras iniciar sesión, porque desde el catálogo se inscribe, y para eso sí hace
 * falta sesión. Ofrecerlo sin ella llevaría a un botón que siempre falla.
 */

import type {
  CourseDetail,
  CourseOfferings,
  CurrentPeriod,
  Course,
  FiltrosCatalogo,
  Offering,
  Page,
  StudyPlan,
} from "@/features/catalog/api/types";
import { api } from "@/lib/api/client";

/** Lista materias del catálogo aplicando los filtros. */
export function listarMaterias(filtros: FiltrosCatalogo, signal?: AbortSignal) {
  return api.get<Page<Course>>("/api/v1/courses", {
    // El cliente omite los valores vacíos: un `search=` sin contenido haría que el backend
    // buscara la cadena vacía en vez de devolver el catálogo completo.
    query: {
      page: filtros.page,
      size: filtros.size,
      search: filtros.search,
      program_id: filtros.program_id,
      semester: filtros.semester,
    },
    signal,
  });
}

/**
 * Detalle de una materia con lo que exige dentro de un plan de estudios.
 *
 * `programId` no es opcional por comodidad: sin él el servidor devuelve las listas de
 * requisitos vacías, porque un prerrequisito pertenece a una carrera y no al catálogo. Se
 * envía siempre el del estudiante.
 */
export function obtenerMateria(
  courseId: string,
  programId: string | null,
  signal?: AbortSignal,
) {
  return api.get<CourseDetail>(`/api/v1/courses/${courseId}`, {
    // El cliente omite los valores vacíos, así que `null` equivale a no enviar el parámetro:
    // la materia llega igual y sin requisitos, que es lo correcto cuando no se sabe el plan.
    query: { program_id: programId ?? undefined },
    signal,
  });
}

/** Grupos de una materia en el período activo. */
export function obtenerGrupos(courseId: string, signal?: AbortSignal) {
  return api.get<CourseOfferings>(`/api/v1/courses/${courseId}/offerings`, { signal });
}

/** Detalle de un grupo. */
export function obtenerGrupo(offeringId: string, signal?: AbortSignal) {
  return api.get<Offering>(`/api/v1/offerings/${offeringId}`, { signal });
}

/**
 * Plan de estudios de la carrera del estudiante.
 *
 * Es lo que responde «qué materias son las mías». El catálogo no puede contestarlo: lista
 * TODAS las materias de la institución, así que un estudiante de Derecho veía Programación
 * II y solo al pulsar «Inscribir» recibía un 403.
 *
 * Exige token porque el programa sale de él, no de la petición.
 */
export function obtenerPlanDeEstudios(token: string, signal?: AbortSignal) {
  return api.get<StudyPlan>("/api/v1/students/me/study-plan", { token, signal });
}

/** Período de matrícula vigente. Responde 404 cuando no hay ninguno activo. */
export function obtenerPeriodoActual(signal?: AbortSignal) {
  return api.get<CurrentPeriod>("/api/v1/enrollment-periods/current", { signal });
}

/**
 * Claves de caché del catálogo.
 *
 * Se construyen aquí, en un solo sitio, por la misma razón que en el backend: una clave
 * escrita a mano en dos pantallas acaba divergiendo, y entonces invalidar una no invalida la
 * otra. Al incluir los filtros, cada combinación es una entrada distinta y dos búsquedas
 * diferentes no comparten resultado.
 */
export const clavesCatalogo = {
  todo: ["catalogo"] as const,
  materias: (filtros: FiltrosCatalogo) => ["catalogo", "materias", filtros] as const,
  // El programa entra en la clave porque cambia la RESPUESTA: la misma materia exige
  // cosas distintas en dos carreras, y compartir entrada haría que la ficha mostrara los
  // requisitos del plan de la sesión anterior.
  materia: (courseId: string, programId: string) =>
    ["catalogo", "materia", courseId, programId] as const,
  grupos: (courseId: string) => ["catalogo", "grupos", courseId] as const,
  periodoActual: ["catalogo", "periodo-actual"] as const,
  planDeEstudios: ["catalogo", "plan-de-estudios"] as const,
};
