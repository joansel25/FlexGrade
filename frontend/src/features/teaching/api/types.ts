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
