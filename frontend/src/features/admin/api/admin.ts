/**
 * Llamadas a los endpoints de administración.
 *
 * Todos exigen token con rol ADMIN: el backend lo declara una sola vez en el router, no
 * endpoint por endpoint. Aquí no se comprueba nada de eso —comprobarlo en el cliente sería
 * duplicar una regla que no protege nada—, solo se envía el token.
 */

import type { EnrollmentReport, OccupancyReport } from "@/features/admin/api/types";
import { api } from "@/lib/api/client";

/** Cifras de matrícula del período activo, calculadas en vivo. */
export function obtenerReporteDeInscripciones(token: string, signal?: AbortSignal) {
  return api.get<EnrollmentReport>("/api/v1/admin/reports/enrollments", { token, signal });
}

/**
 * Ocupación de los grupos, del más lleno al más vacío.
 *
 * `size` pequeño a propósito en el panel: lo que hay que vigilar son los que están a punto de
 * llenarse, y esos son los primeros. Traer trescientos grupos para mostrar cinco sería mover
 * datos que nadie mira.
 */
export function obtenerReporteDeOcupacion(
  token: string,
  { size = 5 }: { size?: number } = {},
  signal?: AbortSignal,
) {
  return api.get<OccupancyReport>("/api/v1/admin/reports/occupancy", {
    query: { page: 1, size },
    token,
    signal,
  });
}

/** Claves de caché de administración, en un solo sitio como en el resto de la aplicación. */
export const clavesAdmin = {
  todo: ["admin"] as const,
  inscripciones: ["admin", "reporte-inscripciones"] as const,
  ocupacion: (size: number) => ["admin", "reporte-ocupacion", size] as const,
};
