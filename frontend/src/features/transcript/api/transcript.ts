/**
 * Llamada al expediente académico.
 *
 * Es el dato más sensible que guarda el sistema —notas, materias perdidas, cuántas veces se
 * repitió algo—, así que el endpoint no lleva identificador en la ruta: el estudiante sale del
 * token. Por eso aquí el token es un parámetro obligatorio y no una opción.
 */

import type { AcademicHistory } from "@/features/transcript/api/types";
import { api } from "@/lib/api/client";

/** Expediente de quien tiene la sesión abierta. */
export function obtenerExpediente(token: string, signal?: AbortSignal) {
  return api.get<AcademicHistory>("/api/v1/students/me/history", { token, signal });
}

/**
 * Claves de caché del expediente.
 *
 * No llevan el estudiante dentro porque tampoco lo lleva la petición: el expediente es siempre
 * el de la sesión. Al cerrarla se vacía la caché entera de TanStack Query, así que la siguiente
 * persona en el mismo navegador no puede ver un instante el expediente de la anterior.
 */
export const clavesExpediente = {
  todo: ["expediente"] as const,
  mio: ["expediente", "mio"] as const,
};
