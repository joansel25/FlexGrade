/** Tipos de la carga docente (`API.md` sección 8). */

import type { ScheduleBlock } from "@/features/catalog/api/types";

/**
 * Un grupo visto por quien lo dicta.
 *
 * Se parece a `Offering` pero no es lo mismo, y unificarlos sería un error: aquel es la vista
 * del catálogo —cupos libres y nombre del docente, que es lo que importa a quien busca dónde
 * matricularse— y aquí el docente es quien mira, así que su propio nombre sobra y en cambio
 * necesita la materia y cuántos estudiantes tiene enfrente.
 */
export interface ProfessorOffering {
  offering_id: string;
  course_id: string;
  course_code: string;
  course_name: string;
  credits: number;
  group_number: string;
  enrolled_count: number;
  total_capacity: number;
  schedule: ScheduleBlock[];
}

/**
 * Respuesta de `GET /professors/me/offerings`.
 *
 * `period_code` en `null` significa que no hay ventana activa, que entre semestres es normal.
 * Distingue ese caso de «hay semestre y no tengo carga», que se ve igual —una lista vacía— y
 * quiere decir algo muy distinto.
 */
export interface ProfessorOfferings {
  period_code: string | null;
  academic_period: string | null;
  items: ProfessorOffering[];
  total: number;
}

/**
 * Una fila de la lista del grupo.
 *
 * `final_grade` en `null` es «todavía sin calificar», y es distinto de `"0.00"`. Son estados
 * opuestos —uno es que falta trabajo, el otro es una nota reprobatoria— y con un cero por
 * defecto se verían igual.
 *
 * Llega como `string` y no como `number` porque el servidor la manda con dos decimales exactos
 * y `JSON.parse` la convertiría en un `double`: `4.25` sobrevive, pero el redondeo de la
 * frontera de aprobación no es algo que convenga dejar en manos de la coma flotante.
 */
export interface GradeEntry {
  student_id: string;
  student_code: string;
  full_name: string;
  final_grade: string | null;
  graded_at: string | null;
}

/** Respuesta de `GET /professors/me/offerings/{id}/roster`. */
export interface OfferingRoster {
  offering_id: string;
  course_code: string;
  course_name: string;
  group_number: string;
  entries: GradeEntry[];
  total: number;
  /** Cuántas quedan sin calificar. Es la cifra que dice si el trabajo terminó. */
  pending: number;
}
