/**
 * Hook del estado del servicio.
 *
 * Vive aparte del componente para que la pantalla no sepa nada de TanStack Query: si algún día
 * se cambia la librería de estado del servidor, se reescribe este archivo y ningún componente
 * se entera. Es la misma idea de los puertos del backend, aplicada al frontend.
 */

import { useQuery } from "@tanstack/react-query";

import { CLAVE_ESTADO_SERVICIO, obtenerEstadoServicio } from "@/features/health/api/health";

/** Cada cuánto se vuelve a comprobar el estado del servicio. */
const INTERVALO_MS = 60_000;

export function useServiceStatus() {
  return useQuery({
    queryKey: CLAVE_ESTADO_SERVICIO,
    queryFn: ({ signal }) => obtenerEstadoServicio(signal),
    // Se refresca solo, pero sin insistir: es información de contexto, no el dato por el que
    // el estudiante entró. Un intervalo corto multiplicaría peticiones sin aportar nada.
    refetchInterval: INTERVALO_MS,
    staleTime: INTERVALO_MS,
    // Un solo reintento: si la API no responde, lo útil es DECIRLO cuanto antes en vez de
    // dejar el indicador en "comprobando" durante medio minuto.
    retry: 1,
  });
}
