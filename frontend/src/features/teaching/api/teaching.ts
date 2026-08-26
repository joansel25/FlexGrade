/** Cliente de los endpoints del docente. */

import type { ProfessorOfferings } from "@/features/teaching/api/types";
import { api } from "@/lib/api/client";

/**
 * Los grupos que dicta quien pregunta, en la ventana activa.
 *
 * No recibe identificador de docente y no es un olvido: el backend lo saca del token. Una ruta
 * con el identificador dentro permitiría pedir la carga de otro, y la única defensa sería
 * acordarse de comprobarlo en cada endpoint.
 */
export function obtenerMisGrupos(token: string, signal?: AbortSignal) {
  return api.get<ProfessorOfferings>("/api/v1/professors/me/offerings", { token, signal });
}
