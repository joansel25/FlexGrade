/**
 * Tipos de los reportes de administración (`API.md` sección 6).
 */

/** Cifras globales del período. */
export interface ReportTotals {
  total_enrollments: number;
  unique_students: number;
  active_offerings: number;
}

/** Inscripciones de un programa dentro del período. */
export interface ProgramEnrollments {
  program_code: string;
  program_name: string;
  enrollments: number;
  students: number;
}

/** Respuesta de `GET /admin/reports/enrollments`. */
export interface EnrollmentReport {
  period_code: string;
  /** Instante del cálculo. Se muestra: un reporte sin hora no se sabe si es de ahora. */
  generated_at: string;
  totals: ReportTotals;
  by_program: ProgramEnrollments[];
}

/** Ocupación de un grupo. */
export interface OfferingOccupancy {
  offering_id: string;
  course_code: string;
  course_name: string;
  group_number: string;
  total_capacity: number;
  enrolled_count: number;
  available_slots: number;
  /** Porcentaje de 0 a 100, ya calculado en el servidor. */
  occupancy_rate: number;
}

/**
 * Respuesta de `GET /admin/reports/occupancy`.
 *
 * Llega ordenada del grupo más lleno al más vacío, y ese orden no es cosmético: la primera
 * página son los grupos a punto de llenarse, que son sobre los que hay que decidir si se amplía
 * el cupo o se abre otro grupo.
 */
export interface OccupancyReport {
  period_code: string;
  generated_at: string;
  offerings: OfferingOccupancy[];
  total: number;
  page: number;
  size: number;
}
