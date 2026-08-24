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

export const handlers = [
  http.get(`${API_URL}/health`, () => HttpResponse.json(ESTADO_SANO)),
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
