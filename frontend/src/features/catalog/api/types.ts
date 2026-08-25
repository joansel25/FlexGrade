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

/**
 * Detalle de una materia, con lo que exige DENTRO de un plan de estudios.
 *
 * Los requisitos son DIRECTOS, no el cierre transitivo: si `MAT201` exige `MAT102` y esta
 * exige `MAT101`, la ficha de `MAT201` muestra solo `MAT102`.
 *
 * Las dos listas solo llegan llenas si la petición indicó `program_id`. Un requisito no une
 * dos materias sino dos materias dentro de una carrera, así que sin plan el servidor no tiene
 * una respuesta correcta que dar y devuelve `program_id: null` para decirlo.
 */
export interface CourseDetail extends Course {
  /** Plan sobre el que se resolvieron los requisitos; `null` si no se preguntó por ninguno. */
  program_id: string | null;
  /** Materias que hay que haber APROBADO antes. */
  prerequisites: Course[];
  /** Materias que hay que cursar EN EL MISMO período. */
  corequisites: Course[];
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
/**
 * En qué punto está el estudiante respecto a una materia de su plan.
 *
 * Lo calcula el SERVIDOR con los mismos servicios de dominio que deciden si una inscripción se
 * acepta. El frontend no vuelve a razonar la regla: una segunda versión aquí funcionaría el
 * primer día y discreparía el día que una de las dos cambiara, dejando la pantalla ofreciendo
 * lo que el servidor rechaza.
 */
export type CourseStatus =
  /** Ya la aprobó. No hay nada que hacer. */
  | "APPROVED"
  /** La está cursando en el período vigente. */
  | "ENROLLED"
  /** Puede inscribirla ahora mismo. Es la única sobre la que se pulsa. */
  | "AVAILABLE"
  /** Cumple los requisitos, pero no hay grupos este período. */
  | "NOT_OFFERED"
  /** Le falta algo; `missing_prerequisites` y `missing_corequisites` dicen qué. */
  | "BLOCKED";

export interface StudyPlanEntry extends Course {
  /** Semestre en que el plan la sugiere. */
  suggested_semester: number;
  /** Obligatoria para graduarse, o electiva. */
  is_mandatory: boolean;
  status: CourseStatus;
  /** Códigos por aprobar. Solo llega con `BLOCKED`. */
  missing_prerequisites: string[];
  /** Códigos que habría que cursar a la vez y no se ofrecen. Solo llega con `BLOCKED`. */
  missing_corequisites: string[];
  /**
   * Códigos que hay que inscribir junto a esta materia.
   *
   * Llega siempre que existan, también cuando la materia está disponible: es una instrucción,
   * no un impedimento, y esconderla hasta que la inscripción falle sería repetir el error que
   * arregló la 6.1.
   */
  corequisites: string[];
}

/** Respuesta de `GET /students/me/study-plan`. */
export interface StudyPlan {
  /** Identificador del programa. Es lo que la ficha de una materia envía para saber qué exige. */
  program_id: string;
  program_code: string;
  program_name: string;
  total_semesters: number;
  courses: StudyPlanEntry[];
  total_credits: number;
  /** Créditos ya aprobados. Responde «cuánto llevo» sin que la pantalla recorra la lista. */
  approved_credits: number;
}
