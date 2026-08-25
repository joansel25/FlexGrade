/**
 * Tipos del catálogo académico (`API.md` sección 3).
 */

/** Una materia del catálogo. */
export interface Course {
  id: string;
  code: string;
  name: string;
  credits: number;
  description: string | null;
}

/** Detalle de una materia, con sus prerrequisitos DIRECTOS (no el cierre transitivo). */
export interface CourseDetail extends Course {
  prerequisites: Course[];
}

/** Envoltorio de las respuestas paginadas. */
export interface Page<T> {
  items: T[];
  /** Total de coincidencias, no solo las de esta página. */
  total: number;
  page: number;
  size: number;
}

/** Una franja horaria semanal. */
export interface ScheduleBlock {
  /** 1 = lunes … 7 = domingo (ISO 8601). */
  day_of_week: number;
  /** Hora en formato `HH:MM` o `HH:MM:SS`. */
  start_time: string;
  end_time: string;
  classroom: string | null;
}

/** Un grupo de una materia. */
export interface Offering {
  id: string;
  group_number: string;
  professor: string | null;
  total_capacity: number;
  /**
   * Cupos ocupados. Se lee SIEMPRE en vivo de PostgreSQL, incluso cuando el resto del grupo
   * viene de la caché de Redis (`API.md` sección 3).
   */
  enrolled_count: number;
  available_slots: number;
  schedule: ScheduleBlock[];
}

/** Respuesta de `GET /courses/{id}/offerings`. */
export interface CourseOfferings {
  course_id: string;
  course_code: string;
  period_code: string;
  offerings: Offering[];
}

/** Respuesta de `GET /enrollment-periods/current`. */
export interface CurrentPeriod {
  id: string;
  code: string;
  academic_period: string;
  name: string;
  starts_at: string;
  ends_at: string;
  /** Si un administrador activó la ventana. */
  is_active: boolean;
  /**
   * Si admite inscripciones en ESTE instante. No es lo mismo que `is_active`: una ventana
   * activada puede no haber empezado o haber cerrado ya, y esa diferencia es la que permite
   * mostrar «la matrícula abre el martes» en vez de un botón que fallará.
   */
  is_open: boolean;
  /** Segundos hasta el cierre; `0` si ya cerró. */
  time_remaining_seconds: number;
}

/** Filtros de `GET /courses`. */
export interface FiltrosCatalogo {
  search?: string;
  program_id?: string;
  semester?: number;
  page: number;
  size: number;
}

/** Una materia dentro del plan de estudios del estudiante. */
export interface StudyPlanEntry extends Course {
  /** Semestre en que el plan la sugiere. */
  suggested_semester: number;
  /** Obligatoria para graduarse, o electiva. */
  is_mandatory: boolean;
}

/** Respuesta de `GET /students/me/study-plan`. */
export interface StudyPlan {
  program_code: string;
  program_name: string;
  total_semesters: number;
  courses: StudyPlanEntry[];
  total_credits: number;
}
