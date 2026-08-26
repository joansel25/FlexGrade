/**
 * Hooks del panel de administración.
 *
 * Los dos reportes se consideran SIEMPRE obsoletos (`staleTime: 0`) y se refrescan solos cada
 * treinta segundos. Es la misma razón por la que el backend no los cachea: son las cifras que
 * se consultan MIENTRAS la matrícula ocurre, y un número de hace un minuto que parece actual es
 * peor que no tener panel — lleva a decidir sobre un cupo que ya no existe.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  activarPeriodo,
  ajustarCupo,
  clavesAdmin,
  crearGrupo,
  crearMateria,
  crearPeriodo,
  listarPeriodos,
  obtenerReporteDeInscripciones,
  obtenerReporteDeOcupacion,
} from "@/features/admin/api/admin";
import type {
  NewCourse,
  NewEnrollmentPeriod,
  NewOffering,
} from "@/features/admin/api/types";
import { clavesCatalogo } from "@/features/catalog/api/catalog";
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

/** Las ventanas de matrícula, de la más reciente a la más antigua. */
export function usePeriods() {
  const { accessToken, habilitado } = useSesion();

  return useQuery({
    queryKey: clavesAdmin.periodos,
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return listarPeriodos(accessToken, signal);
    },
    enabled: habilitado,
    staleTime: 0,
  });
}

/**
 * Invalida lo que una operación de administración deja obsoleto.
 *
 * Se invalida TODO el espacio de administración y también el del catálogo, en un solo sitio.
 * Repartir la lista por cada formulario es la forma segura de que alguno se olvide, y el
 * síntoma sería una materia recién creada que no aparece en la lista de al lado.
 */
function useInvalidarAdmin() {
  const queryClient = useQueryClient();

  return () => {
    void queryClient.invalidateQueries({ queryKey: clavesAdmin.todo });
    void queryClient.invalidateQueries({ queryKey: clavesCatalogo.todo });
  };
}

function useTokenObligatorio() {
  const { accessToken } = useAuth();

  return () => {
    if (accessToken === null) {
      throw new Error("No hay sesión activa");
    }

    return accessToken;
  };
}

/** Abre una ventana de matrícula. Nace inactiva. */
export function useCreatePeriod() {
  const token = useTokenObligatorio();
  const invalidar = useInvalidarAdmin();

  return useMutation({
    mutationFn: (payload: NewEnrollmentPeriod) => crearPeriodo(payload, token()),
    onSuccess: invalidar,
  });
}

/** Activa una ventana y cierra la que estuviera abierta. */
export function useActivatePeriod() {
  const token = useTokenObligatorio();
  const invalidar = useInvalidarAdmin();

  return useMutation({
    mutationFn: (periodId: string) => activarPeriodo(periodId, token()),
    onSuccess: invalidar,
  });
}

/** Crea una materia del catálogo. */
export function useCreateCourse() {
  const token = useTokenObligatorio();
  const invalidar = useInvalidarAdmin();

  return useMutation({
    mutationFn: (payload: NewCourse) => crearMateria(payload, token()),
    onSuccess: invalidar,
  });
}

/** Abre un grupo en el período activo. */
export function useCreateOffering() {
  const token = useTokenObligatorio();
  const invalidar = useInvalidarAdmin();

  return useMutation({
    mutationFn: (payload: NewOffering) => crearGrupo(payload, token()),
    onSuccess: invalidar,
  });
}

/** Ajusta el cupo total de un grupo. */
export function useAdjustCapacity() {
  const token = useTokenObligatorio();
  const invalidar = useInvalidarAdmin();

  return useMutation({
    mutationFn: ({ offeringId, totalCapacity }: { offeringId: string; totalCapacity: number }) =>
      ajustarCupo(offeringId, totalCapacity, token()),
    onSuccess: invalidar,
  });
}
