/**
 * Llamadas a los endpoints de inscripción y horario.
 *
 * Todos exigen token: el estudiante sale SIEMPRE del token, nunca del cuerpo ni de la URL. Es
 * lo que hace imposible inscribir o cancelar en nombre de otra persona, y por eso ninguna de
 * estas funciones recibe un `student_id`.
 */

import type {
  Cancellation,
  Enrollment,
  StudentEnrollments,
  StudentSchedule,
} from "@/features/enrollment/api/types";
import { api } from "@/lib/api/client";

/** Inscribe al estudiante autenticado en un grupo. */
export function inscribir(courseOfferingId: string, token: string, signal?: AbortSignal) {
  return api.post<Enrollment>("/api/v1/enrollments", {
    body: { course_offering_id: courseOfferingId },
    token,
    signal,
  });
}

/**
 * Cancela una inscripción y libera el cupo.
 *
 * Devuelve QUÉ se canceló, y no `void`, porque la operación puede arrastrar más de una
 * inscripción: las materias unidas por correquisitos mutuos se abandonan como un bloque. Sin
 * ese dato la pantalla no podría explicar por qué desaparecieron dos materias al cancelar una.
 *
 * Cancelar una inscripción ajena responde 404, igual que si no existiera: un 403 confirmaría
 * que ese identificador corresponde a una inscripción real.
 */
export function cancelar(enrollmentId: string, token: string, signal?: AbortSignal) {
  return api.delete<Cancellation>(`/api/v1/enrollments/${enrollmentId}`, { token, signal });
}

/** Inscripciones activas del estudiante en el período vigente. */
export function listarInscripciones(token: string, signal?: AbortSignal) {
  return api.get<StudentEnrollments>("/api/v1/students/me/enrollments", { token, signal });
}

/** Horario armado del estudiante. */
export function obtenerHorario(token: string, signal?: AbortSignal) {
  return api.get<StudentSchedule>("/api/v1/students/me/schedule", { token, signal });
}

/** Claves de caché del flujo de inscripción. */
export const clavesInscripcion = {
  todo: ["inscripciones"] as const,
  mias: ["inscripciones", "mias"] as const,
  horario: ["inscripciones", "horario"] as const,
};
