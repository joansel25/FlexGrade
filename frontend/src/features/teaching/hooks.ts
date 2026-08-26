/** Hooks de la carga docente. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/useAuth";
import { obtenerLista, obtenerMisGrupos, ponerNota } from "@/features/teaching/api/teaching";

export const clavesDocencia = {
  raiz: ["docencia"] as const,
  misGrupos: ["docencia", "mis-grupos"] as const,
  lista: (offeringId: string) => ["docencia", "lista", offeringId] as const,
};

/**
 * Los grupos del docente en el período activo.
 *
 * `staleTime` en 0 como el resto de lo que muestra cupos: `enrolled_count` cambia mientras la
 * matrícula ocurre, y servirlo de una caché haría que el docente viera una clase más pequeña de
 * la que tiene.
 */
export function useMyTeachingLoad() {
  const { accessToken, estado } = useAuth();

  return useQuery({
    queryKey: clavesDocencia.misGrupos,
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return obtenerMisGrupos(accessToken, signal);
    },
    enabled: estado === "autenticado" && accessToken !== null,
    staleTime: 0,
  });
}

/** La lista de un grupo. */
export function useOfferingRoster(offeringId: string | null) {
  const { accessToken, estado } = useAuth();

  return useQuery({
    queryKey: clavesDocencia.lista(offeringId ?? ""),
    queryFn: ({ signal }) => {
      if (accessToken === null || offeringId === null) {
        throw new Error("No hay grupo que consultar");
      }

      return obtenerLista(offeringId, accessToken, signal);
    },
    enabled: estado === "autenticado" && accessToken !== null && offeringId !== null,
    staleTime: 0,
  });
}

/**
 * Registra o corrige una nota.
 *
 * Invalida la lista al terminar y no actualiza el estado local: el servidor es quien decide
 * cómo queda la nota —la normaliza a dos decimales— y quien cuenta cuántas faltan. Escribirlo
 * en el cliente pintaría un número que puede no ser el guardado.
 */
export function useSetGrade(offeringId: string) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ studentId, nota }: { studentId: string; nota: string }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return ponerNota(offeringId, studentId, nota, accessToken);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: clavesDocencia.raiz }),
  });
}
