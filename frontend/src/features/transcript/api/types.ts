/**
 * Tipos del expediente académico (iteración 9.4).
 *
 * **Las notas y los promedios llegan como `string`, y aquí se quedan así.** El backend los
 * modela con `Decimal` y los serializa con dos decimales exactos precisamente para que un
 * `4.25` no dependa de la coma flotante; convertirlos a `number` en la pantalla desharía esa
 * decisión en el último paso, justo en la cifra que decide una beca o aparece en un
 * certificado. La pantalla los PINTA, no opera con ellos.
 */

/** Cómo terminó una materia. Lo deriva el servidor de la nota, nunca el cliente. */
export type HistoryStatus = "APPROVED" | "FAILED";

/**
 * Una materia cursada, con su resultado.
 *
 * La misma materia puede aparecer en VARIOS semestres —quien la perdió y la repitió tiene las
 * dos filas—, así que `course_id` identifica la materia, no la fila del expediente. Dentro de
 * un semestre sí es único: lo garantiza el `UNIQUE (student_id, course_id, academic_period)`
 * de la base.
 */
export interface HistoryEntry {
  course_id: string;
  code: string;
  name: string;
  credits: number;
  final_grade: string;
  status: HistoryStatus;
}

/**
 * Lo cursado en un semestre.
 *
 * `average` es el promedio PONDERADO POR CRÉDITOS del semestre, calculado en el servidor. La
 * pantalla no lo recalcula: una media simple daría otro número y quien lo viera lo tomaría por
 * el oficial.
 */
export interface HistoryPeriod {
  academic_period: string;
  entries: HistoryEntry[];
  credits_attempted: number;
  credits_approved: number;
  average: string;
}

/**
 * Respuesta de `GET /students/me/history`.
 *
 * Los semestres vienen del más reciente al más antiguo, que es como se lee un expediente.
 * `periods: []` es una respuesta legítima y no un error: quien acaba de ingresar todavía no ha
 * cerrado ningún semestre.
 */
export interface AcademicHistory {
  student_code: string;
  full_name: string;
  periods: HistoryPeriod[];
  total_credits_approved: number;
  cumulative_average: string;
}
