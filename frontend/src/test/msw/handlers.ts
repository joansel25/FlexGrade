/**
 * Respuestas simuladas de la API para los tests.
 *
 * Se usa MSW (Mock Service Worker), que intercepta a nivel de red en vez de sustituir `fetch`
 * con un doble. La diferencia importa: con MSW se prueba el cliente HTTP de verdad —cabeceras,
 * códigos de estado, interpretación del cuerpo de error— y no una versión falsa de él que
 * siempre se comporta bien.
 */

import { HttpResponse, http } from "msw";

/** Base que usan los tests; coincide con la de `.env.example`. */
export const API_URL = "http://localhost:8000";

/** Estado del servicio con el que responde el backend cuando todo va bien. */
export const ESTADO_SANO = {
  status: "ok",
  environment: "test",
  version: "0.1.0",
};

/** Cuenta con la que se autentican los tests. */
export const USUARIO = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "estudiante@tdea.edu.co",
  role: "STUDENT" as const,
};

/** Perfil que devuelve `GET /students/me`. */
export const PERFIL = {
  id: "22222222-2222-2222-2222-222222222222",
  student_code: "1234567",
  full_name: "Joan Sebastián Cárdenas",
  email: USUARIO.email,
  program: {
    id: "33333333-3333-3333-3333-333333333333",
    code: "ISIS",
    name: "Ingeniería de Sistemas",
  },
  current_semester: 6,
  enrollment_date: "2022-01-15",
};

export const CREDENCIALES_VALIDAS = { email: USUARIO.email, password: "SecurePass123" };

/** Par de tokens con la forma que promete `API.md`. */
export function parDeTokens(sufijo = "1") {
  return {
    access_token: `access-${sufijo}`,
    refresh_token: `refresh-${sufijo}`,
    token_type: "bearer",
    expires_in: 3600,
  };
}

export const handlers = [
  http.get(`${API_URL}/health`, () => HttpResponse.json(ESTADO_SANO)),

  http.post(`${API_URL}/api/v1/auth/login`, async ({ request }) => {
    const cuerpo = (await request.json()) as { email: string; password: string };

    if (
      cuerpo.email !== CREDENCIALES_VALIDAS.email ||
      cuerpo.password !== CREDENCIALES_VALIDAS.password
    ) {
      return respuestaDeError(401, "INVALID_CREDENTIALS", "Correo o contraseña incorrectos");
    }

    return HttpResponse.json({ ...parDeTokens(), user: USUARIO });
  }),

  http.post(`${API_URL}/api/v1/auth/refresh`, () => HttpResponse.json(parDeTokens("renovado"))),

  http.post(`${API_URL}/api/v1/auth/logout`, () => new HttpResponse(null, { status: 204 })),

  http.get(`${API_URL}/api/v1/students/me`, ({ request }) => {
    // Se comprueba la cabecera de verdad: es lo que demuestra que el token viaja en cada
    // petición protegida, que es justo lo que esta iteración añade.
    if (!request.headers.get("Authorization")?.startsWith("Bearer ")) {
      return respuestaDeError(401, "MISSING_TOKEN", "Falta el token de acceso");
    }

    return HttpResponse.json(PERFIL);
  }),
];

/** Construye una respuesta de error con el formato universal de `API.md`. */
export function respuestaDeError(
  status: number,
  code: string,
  message: string,
  details?: Record<string, unknown>,
) {
  return HttpResponse.json({ error: { code, message, details: details ?? {} } }, { status });
}
