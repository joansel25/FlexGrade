/**
 * Tipos del contrato de autenticación (`API.md` secciones 1 y 2).
 *
 * Se escriben a mano y no se generan desde OpenAPI a propósito: son cinco formas estables que
 * cambian una vez por semestre, y un generador añadiría un paso de build y un archivo de miles
 * de líneas para ahorrar treinta. Si el contrato creciera mucho, la decisión se revisa.
 */

/** Roles que reconoce el sistema. */
export type UserRole = "STUDENT" | "ADMIN" | "PROFESSOR";

/** Cuerpo de `POST /auth/login`. */
export interface LoginRequest {
  email: string;
  password: string;
}

/** La cuenta autenticada, tal como la devuelve el login. */
export interface AuthenticatedUser {
  id: string;
  email: string;
  role: UserRole;
}

/** Par de tokens que devuelven el login y el refresco. */
export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  /** Vigencia del access token, en segundos. */
  expires_in: number;
}

/** Respuesta de `POST /auth/login`: el par de tokens más la cuenta. */
export interface LoginResponse extends TokenPair {
  user: AuthenticatedUser;
}

/**
 * Respuesta de `POST /auth/refresh`.
 *
 * Lleva la cuenta además de los tokens, y no por comodidad: el refresco es lo que restaura la
 * sesión al recargar la página. Sin este dato se recuperaría el acceso sin saber QUIÉN entró, y
 * las rutas protegidas por rol expulsarían a un administrador legítimo en cuanto recargara.
 */
export interface RefreshResponse extends TokenPair {
  user: AuthenticatedUser;
}

/** Programa académico al que pertenece el estudiante. */
export interface ProgramSummary {
  id: string;
  code: string;
  name: string;
}

/** Respuesta de `GET /students/me`. */
export interface StudentProfile {
  id: string;
  student_code: string;
  full_name: string;
  email: string;
  program: ProgramSummary;
  current_semester: number;
  /** Fecha de ingreso, en formato ISO (`2022-01-15`). */
  enrollment_date: string;
}
