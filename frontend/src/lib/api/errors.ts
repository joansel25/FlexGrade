/**
 * Errores de la API, tipados como lo que son: estados esperados de la interfaz.
 *
 * `API.md` define un formato de error universal —`{ error: { code, message, details } }`— y un
 * catálogo de `code` estables. Esa estabilidad es la razón de este módulo: el `message` está
 * pensado para leerse y puede cambiar de redacción en cualquier momento, así que la interfaz
 * NUNCA debe decidir en función de él. Decide con el `code`.
 *
 * Durante la matrícula esto deja de ser teoría. `COURSE_CAPACITY_EXCEEDED` no es un fallo: es
 * "alguien se te adelantó por medio segundo", y la pantalla tiene que reaccionar refrescando
 * los cupos y ofreciendo otro grupo, no mostrando un mensaje de error genérico.
 */

/** Códigos que la API puede devolver, según `API.md`. */
export const API_ERROR_CODES = [
  // Autenticación y autorización.
  "INVALID_CREDENTIALS",
  "MISSING_TOKEN",
  "INVALID_TOKEN",
  "USER_INACTIVE",
  "ADMIN_REQUIRED",
  "STUDENT_PROFILE_NOT_FOUND",
  // Catálogo.
  "COURSE_NOT_FOUND",
  "OFFERING_NOT_FOUND",
  "PERIOD_NOT_FOUND",
  "PROFESSOR_NOT_FOUND",
  "NO_ACTIVE_PERIOD",
  // Inscripción.
  "ENROLLMENT_PERIOD_INACTIVE",
  "COURSE_CAPACITY_EXCEEDED",
  "ALREADY_ENROLLED",
  "PREREQUISITES_NOT_MET",
  "SCHEDULE_CONFLICT",
  "ENROLLMENT_ALREADY_CANCELLED",
  "COURSE_NOT_IN_PROGRAM",
  "ENROLLMENT_NOT_FOUND",
  // Administración.
  "DUPLICATE_PERIOD_CODE",
  "INVALID_PERIOD_RANGE",
  "DUPLICATE_COURSE_CODE",
  "DUPLICATE_OFFERING_GROUP",
  "CAPACITY_BELOW_ENROLLED",
  "OVERLAPPING_SCHEDULE",
  "CONCURRENT_MODIFICATION",
  // Genéricos.
  "DOMAIN_ERROR",
] as const;

export type ApiErrorCode = (typeof API_ERROR_CODES)[number];

/**
 * Códigos que esta versión del frontend no conoce todavía.
 *
 * El backend puede añadir uno antes de que el frontend se actualice, y ese día la aplicación
 * debe seguir funcionando: se muestra el mensaje del servidor en vez de romperse.
 */
export type ApiErrorCodeOrUnknown = ApiErrorCode | (string & {});

/** Cuerpo de error que promete `API.md`. */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

/**
 * Un error devuelto por la API, con su código y su contexto.
 *
 * Se lanza en vez de devolverse porque TanStack Query distingue éxito de fallo por excepción:
 * devolver un objeto de error haría que una respuesta 409 se tratara como datos válidos y
 * acabara pintada en la pantalla como si fuera un catálogo.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCodeOrUnknown;
  readonly details: Record<string, unknown>;

  constructor(params: {
    status: number;
    code: ApiErrorCodeOrUnknown;
    message: string;
    details?: Record<string, unknown>;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.code = params.code;
    this.details = params.details ?? {};
  }

  /** Indica si el error corresponde a alguno de los códigos indicados. */
  is(...codes: ApiErrorCodeOrUnknown[]): boolean {
    return codes.includes(this.code);
  }

  /** La sesión no vale: hay que renovar el token o volver a iniciar sesión. */
  get isAuthError(): boolean {
    return this.status === 401;
  }

  /**
   * El estado del sistema impide la operación, pero la petición era correcta.
   *
   * Es el caso más frecuente durante la matrícula —cupo agotado, choque de horario— y el que
   * la interfaz debe tratar como información, no como avería.
   */
  get isConflict(): boolean {
    return this.status === 409;
  }
}

/**
 * Fallo de red o de formato: la petición no llegó, o la respuesta no era la esperada.
 *
 * Se distingue de `ApiError` a propósito: aquí el servidor no ha dicho nada, así que la
 * interfaz debe ofrecer reintentar en vez de explicar una regla de negocio que nadie aplicó.
 */
export class NetworkError extends Error {
  readonly cause?: unknown;

  constructor(message: string, cause?: unknown) {
    super(message);
    this.name = "NetworkError";
    this.cause = cause;
  }
}

/** Comprueba si un valor desconocido tiene la forma del cuerpo de error de la API. */
export function esCuerpoDeError(valor: unknown): valor is ApiErrorBody {
  if (typeof valor !== "object" || valor === null || !("error" in valor)) {
    return false;
  }

  // Tras el `in` de arriba, TypeScript ya sabe que la propiedad existe.
  const { error } = valor;

  if (typeof error !== "object" || error === null) {
    return false;
  }

  const { code, message } = error as { code?: unknown; message?: unknown };

  return typeof code === "string" && typeof message === "string";
}
