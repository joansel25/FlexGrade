/** Hooks de la carga docente. */

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/useAuth";
import { obtenerMisGrupos } from "@/features/teaching/api/teaching";

export const clavesDocencia = {
  raiz: ["docencia"] as const,
  misGrupos: ["docencia", "mis-grupos"] as const,
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
