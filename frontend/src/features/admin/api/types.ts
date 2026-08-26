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

/** Una ventana de matrícula, tal como la lista `GET /admin/enrollment-periods`. */
export interface EnrollmentPeriod {
  id: string;
  code: string;
  academic_period: string;
  name: string;
  starts_at: string;
  ends_at: string;
  is_active: boolean;
}

/** Cuerpo de `POST /admin/enrollment-periods`. */
export interface NewEnrollmentPeriod {
  code: string;
  academic_period: string;
  name: string;
  starts_at: string;
  ends_at: string;
}

/** Cuerpo de `POST /admin/courses`. */
export interface NewCourse {
  code: string;
  name: string;
  credits: number;
  description?: string | null;
}

/** Una franja al abrir un grupo: el aula viaja por CÓDIGO, no por identificador. */
export interface NewScheduleBlock {
  day_of_week: number;
  start_time: string;
  end_time: string;
  space_code?: string | null;
}

/** Cuerpo de `POST /admin/offerings`. */
export interface NewOffering {
  course_id: string;
  group_number: string;
  total_capacity: number;
  schedule: NewScheduleBlock[];
}

/** Un espacio libre, tal como lo devuelve `GET /admin/spaces/available`. */
export interface AvailableSpace {
  id: string;
  code: string;
  name: string | null;
  space_type: string;
  capacity: number | null;
  campus: string | null;
  building: string | null;
}

/** Respuesta de `GET /admin/spaces/available`. */
export interface AvailableSpaces {
  day_of_week: number;
  start_time: string;
  end_time: string;
  items: AvailableSpace[];
  total: number;
}

/** Un programa académico. */
export interface Program {
  id: string;
  code: string;
  name: string;
  total_semesters: number;
}

/** Cuerpo de `POST /admin/spaces`. */
export interface NewSpace {
  code: string;
  space_type: string;
  name?: string | null;
  capacity?: number | null;
  campus?: string | null;
  building?: string | null;
}
