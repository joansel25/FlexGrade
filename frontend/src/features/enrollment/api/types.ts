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
