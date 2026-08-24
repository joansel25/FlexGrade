/**
 * Acceso al endpoint de salud del backend.
 *
 * Es la primera conexión real entre frontend y API, y sirve para algo más que decorar: durante
 * el desarrollo distingue "la API está caída" de "mi código está mal", que en local se
 * confunden todo el tiempo. `/health` vive en la RAÍZ, fuera de `/api/v1`, porque lo consume
 * también el balanceador y necesita una ruta fija e independiente de la versión de la API.
 */

import { api } from "@/lib/api/client";

/** Respuesta de `GET /health` (`API.md`). */
export interface EstadoServicio {
  status: string;
  environment: string;
  version: string;
}

/** Consulta el estado del servicio. */
export function obtenerEstadoServicio(signal?: AbortSignal): Promise<EstadoServicio> {
  return api.get<EstadoServicio>("/health", { signal });
}

/** Clave de caché de la consulta, centralizada para poder invalidarla desde cualquier sitio. */
export const CLAVE_ESTADO_SERVICIO = ["health"] as const;
