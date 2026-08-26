/** Cliente de los endpoints del docente. */

import type { OfferingRoster, ProfessorOfferings } from "@/features/teaching/api/types";
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

/** La lista de un grupo, con las notas que ya tiene. */
export function obtenerLista(offeringId: string, token: string, signal?: AbortSignal) {
  return api.get<OfferingRoster>(`/api/v1/professors/me/offerings/${offeringId}/roster`, {
    token,
    signal,
  });
}

/**
 * Registra o corrige la nota de un estudiante.
 *
 * `PUT` porque es idempotente: volver a poner la misma nota deja el mismo estado. Corregir una
 * nota mal tecleada es esta misma llamada, no una operación aparte que haya que recordar.
 */
export function ponerNota(
  offeringId: string,
  studentId: string,
  nota: string,
  token: string,
) {
  return api.put<void>(
    `/api/v1/professors/me/offerings/${offeringId}/grades/${studentId}`,
    { body: { final_grade: nota }, token },
  );
}
