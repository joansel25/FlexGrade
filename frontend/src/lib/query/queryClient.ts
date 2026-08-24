/**
 * Configuración de TanStack Query.
 *
 * Aquí se decide cuánto tiempo se considera fresco un dato y cuándo se reintenta una petición.
 * En una aplicación de matrícula esas dos decisiones no son de rendimiento, son de corrección:
 * un dato servido de más significa mostrar un cupo que ya no existe, y un reintento de más
 * significa insistir contra un servidor que ya dijo que no.
 */

import { QueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/errors";

/**
 * Cuánto dura fresco lo que casi no cambia: el catálogo de materias, los programas.
 *
 * Se alinea con el TTL de la caché de Redis en el backend (30 s). Pedir lo mismo cada pocos
 * segundos desde cinco mil navegadores no aportaría un dato más nuevo: el servidor devolvería
 * la misma entrada cacheada.
 */
export const TIEMPO_FRESCO_CATALOGO_MS = 30_000;

/**
 * Los datos que dependen de cupos NO se consideran frescos nunca.
 *
 * Es la misma regla que sigue el backend (`CLAUDE.md`): la disponibilidad no se cachea. Un
 * número de cupos guardado unos segundos hace que la interfaz mienta justo cuando más
 * importa, y el estudiante intenta inscribir un grupo que ya está lleno.
 */
export const TIEMPO_FRESCO_CUPOS_MS = 0;

/** Número máximo de reintentos para un fallo que sí merece reintentarse. */
const REINTENTOS = 2;

/**
 * Decide si merece la pena reintentar.
 *
 * Un 4xx no se reintenta: el servidor entendió la petición y la rechazó por una razón que no
 * va a cambiar por insistir —sin cupo, sin permiso, sin sesión—. Repetirla solo añade carga en
 * el pico de matrícula y retrasa el mensaje que el estudiante necesita leer.
 *
 * Un 5xx o un fallo de red sí: pueden ser una instancia que el autoescalado está reemplazando,
 * y el balanceador mandará el siguiente intento a otra que sí responde.
 */
function debeReintentar(intentos: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) {
    return false;
  }

  return intentos < REINTENTOS;
}

/** Construye el cliente de consultas con las políticas de la aplicación. */
export function crearQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: TIEMPO_FRESCO_CATALOGO_MS,
        retry: debeReintentar,
        // Al volver a la pestaña se revalida. Durante la matrícula es justo lo que se quiere:
        // quien vuelve tras mirar su horario en otra ventana ve los cupos actuales.
        refetchOnWindowFocus: true,
        // Reintentar al recuperar la conexión evita dejar una pantalla vacía tras un corte.
        refetchOnReconnect: true,
      },
      mutations: {
        // Las mutaciones NUNCA se reintentan solas. Inscribir dos veces por un reintento
        // automático es exactamente el problema que el sistema existe para evitar.
        retry: false,
      },
    },
  });
}
