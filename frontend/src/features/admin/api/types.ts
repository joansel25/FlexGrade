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
  /**
   * Instante en que el semestre se cerró y sus notas pasaron al historial, o `null`.
   *
   * Es una FECHA y no un booleano porque lo primero que se pregunta cuando alguien reclama una
   * nota es si el cierre fue antes o después de que la corrigieran.
   *
   * **`undefined` está en el tipo a propósito.** Durante un tiempo el backend no devolvía este
   * campo en el listado: llegaba AUSENTE, no `null`, y TypeScript no podía verlo porque el tipo
   * afirmaba lo contrario. El resultado fue silencioso y grave —`consolidated_at === null` daba
   * falso para todos los períodos, el botón de cerrar el semestre nunca aparecía y cada ventana
   * anunciaba «Semestre cerrado el Invalid Date»—. Declararlo obliga a comprobarlo con `== null`
   * y a que el compilador exija tratar el caso.
   */
  consolidated_at: string | null | undefined;
}

/** Resumen de un cierre de período. */
export interface Consolidation {
  period_id: string;
  period_code: string;
  academic_period: string;
  consolidated_at: string;
  records: number;
  approved: number;
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

/** Un requisito declarado en el plan, tal como lo ve quien lo edita. */
export interface PlanRequirement {
  course_id: string;
  code: string;
  name: string;
  requirement_type: "PREREQUISITE" | "COREQUISITE";
}

/**
 * Una materia del plan, vista desde administración.
 *
 * No trae los campos del semáforo que sí lleva `StudyPlanEntry`. Aquí no hay persona sobre la
 * que calcularlos, y un `status` con su valor por defecto en todas las materias se lee como un
 * hecho sobre la oferta cuando solo significa «no se calculó».
 */
export interface ProgramPlanEntry {
  id: string;
  code: string;
  name: string;
  credits: number;
  suggested_semester: number;
  is_mandatory: boolean;
  requirements: PlanRequirement[];
}

/** Respuesta de `GET /admin/programs/{id}/plan`. */
export interface ProgramPlan {
  program_id: string;
  program_code: string;
  program_name: string;
  total_semesters: number;
  total_credits: number;
  courses: ProgramPlanEntry[];
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
