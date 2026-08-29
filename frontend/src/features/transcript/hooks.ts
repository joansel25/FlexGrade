/**
 * Hooks del expediente académico.
 *
 * La política de frescura es la contraria a la de los cupos: **el expediente casi nunca
 * cambia**. Solo lo mueve el cierre de un período (`POST /admin/enrollment-periods/{id}/close`),
 * que es una operación de Registro Académico y ocurre una vez por semestre. Refrescarlo al
 * volver a la pestaña gastaría una petición para traer exactamente lo mismo.
 */

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/useAuth";
import { clavesExpediente, obtenerExpediente } from "@/features/transcript/api/transcript";

/** Cinco minutos: el expediente solo cambia cuando se consolida un período. */
const TIEMPO_FRESCO_EXPEDIENTE_MS = 5 * 60_000;

/** Expediente académico de quien tiene la sesión abierta. */
export function useAcademicHistory() {
  const { accessToken, estado } = useAuth();

  return useQuery({
    queryKey: clavesExpediente.mio,
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return obtenerExpediente(accessToken, signal);
    },
    // Sin sesión resuelta no se pide: la consulta saldría sin token y volvería con un 401 que
    // la pantalla mostraría como si el expediente hubiera fallado.
    enabled: estado === "autenticado" && accessToken !== null,
    staleTime: TIEMPO_FRESCO_EXPEDIENTE_MS,
    refetchOnWindowFocus: false,
  });
}
