/**
 * Hooks del panel de administración.
 *
 * Los dos reportes se consideran SIEMPRE obsoletos (`staleTime: 0`) y se refrescan solos cada
 * treinta segundos. Es la misma razón por la que el backend no los cachea: son las cifras que
 * se consultan MIENTRAS la matrícula ocurre, y un número de hace un minuto que parece actual es
 * peor que no tener panel — lleva a decidir sobre un cupo que ya no existe.
 */

import { useQuery } from "@tanstack/react-query";

import {
  clavesAdmin,
  obtenerReporteDeInscripciones,
  obtenerReporteDeOcupacion,
} from "@/features/admin/api/admin";
import { useAuth } from "@/features/auth/useAuth";

/** Cada cuánto se refrescan solos los reportes del panel. */
const INTERVALO_MS = 30_000;

function useSesion() {
  const { accessToken, estado } = useAuth();

  return { accessToken, habilitado: estado === "autenticado" && accessToken !== null };
}

/** Cifras de matrícula del período activo. */
export function useEnrollmentReport() {
  const { accessToken, habilitado } = useSesion();

  return useQuery({
    queryKey: clavesAdmin.inscripciones,
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return obtenerReporteDeInscripciones(accessToken, signal);
    },
    enabled: habilitado,
    staleTime: 0,
    refetchInterval: INTERVALO_MS,
  });
}

/** Los grupos más llenos del período. */
export function useOccupancyReport(size = 5) {
  const { accessToken, habilitado } = useSesion();

  return useQuery({
    queryKey: clavesAdmin.ocupacion(size),
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return obtenerReporteDeOcupacion(accessToken, { size }, signal);
    },
    enabled: habilitado,
    staleTime: 0,
    refetchInterval: INTERVALO_MS,
  });
}
