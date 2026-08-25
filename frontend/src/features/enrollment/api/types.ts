/**
 * Tipos del flujo de inscripción (`API.md` secciones 2 y 4).
 */

import type { ScheduleBlock } from "@/features/catalog/api/types";

/** Respuesta 201 de `POST /enrollments`. */
export interface Enrollment {
  id: string;
  student_id: string;
  course_offering_id: string;
  course_code: string;
  course_name: string;
  group_number: string;
  enrolled_at: string | null;
  status: string;
}

/**
 * Una inscripción activa tal como la lista `GET /students/me/enrollments`.
 *
 * Lleva `id` —el de la INSCRIPCIÓN, no el del grupo— porque es lo que exige la cancelación.
 */
export interface StudentEnrollment {
  id: string;
  course_offering_id: string;
  course_id: string;
  course_code: string;
  course_name: string;
  credits: number;
  group_number: string;
  professor: string | null;
  schedule: ScheduleBlock[];
  enrolled_at: string | null;
  /**
   * Códigos que esta materia exige cursar a la vez y que todavía NO están inscritos.
   *
   * Casi siempre vacío: la inscripción no acepta que falte un correquisito. La excepción es el
   * bloque de correquisitos mutuos —la teoría y su laboratorio—, que se permite inscribir de
   * una en una porque exigir la otra por adelantado haría imposible entrar en ninguna. Entre
   * la primera y la segunda hay un instante con media pareja inscrita, y esto es lo que lo
   * hace visible.
   */
  pending_corequisites: string[];
}

/** Una inscripción que quedó cancelada. */
export interface CancelledEnrollment {
  id: string;
  course_offering_id: string;
  course_code: string;
  course_name: string;
  group_number: string;
}

/**
 * Respuesta de `DELETE /enrollments/{id}`.
 *
 * Es una LISTA porque cancelar puede arrastrar más de una inscripción: las materias unidas por
 * correquisitos mutuos se abandonan como un bloque, igual que se cursan como un bloque.
 */
export interface Cancellation {
  cancelled: CancelledEnrollment[];
}

/** Respuesta de `GET /students/me/enrollments`. */
export interface StudentEnrollments {
  period: string;
  period_code: string;
  items: StudentEnrollment[];
  /** Créditos inscritos, sumados en el servidor para que coincidan con el comprobante. */
  total_credits: number;
}

/** Una franja del horario del estudiante, con el contexto de su materia. */
export interface StudentScheduleBlock {
  course_code: string;
  course_name: string;
  group_number: string;
  professor: string | null;
  day_of_week: number;
  start_time: string;
  end_time: string;
  classroom: string | null;
}

/** Respuesta de `GET /students/me/schedule`. */
export interface StudentSchedule {
  period: string;
  blocks: StudentScheduleBlock[];
}
