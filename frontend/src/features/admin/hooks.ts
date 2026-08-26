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
  consultarDisponibilidad,
  crearEspacio,
  crearGrupo,
  crearMateria,
  crearPeriodo,
  listarEspacios,
  listarPeriodos,
  listarProgramas,
  obtenerPlanDePrograma,
  ponerRequisito,
  quitarRequisito,
  ponerMateriaEnPlan,
  quitarMateriaDelPlan,
  obtenerReporteDeInscripciones,
  obtenerReporteDeOcupacion,
} from "@/features/admin/api/admin";
import type {
  NewCourse,
  NewEnrollmentPeriod,
  NewOffering,
  NewSpace,
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

/** Programas académicos, para elegir cuál plan editar. */
export function usePrograms() {
  const { accessToken, habilitado } = useSesion();

  return useQuery({
    queryKey: clavesAdmin.programas,
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return listarProgramas(accessToken, signal);
    },
    enabled: habilitado,
    // Los programas cambian una vez cada varios años, al contrario que todo lo demás de este
    // panel. Cinco minutos evita pedirlos en cada render de la pantalla.
    staleTime: 5 * 60_000,
  });
}

/** Plan de estudios de un programa concreto. */
export function useProgramPlan(programId: string | null) {
  const { accessToken, habilitado } = useSesion();

  return useQuery({
    queryKey: clavesAdmin.plan(programId ?? ""),
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return obtenerPlanDePrograma(programId ?? "", accessToken, signal);
    },
    enabled: habilitado && programId !== null,
    staleTime: 0,
  });
}

/** Inventario de espacios. */
export function useSpaces(filtros: { space_type?: string } = {}) {
  const { accessToken, habilitado } = useSesion();

  return useQuery({
    queryKey: clavesAdmin.espacios(filtros),
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return listarEspacios(filtros, accessToken, signal);
    },
    enabled: habilitado,
    staleTime: 0,
  });
}

/**
 * Espacios libres en una franja.
 *
 * Solo consulta cuando hay una franja completa: sin día y horas no hay pregunta que hacer, y
 * lanzar la consulta con valores a medias devolvería una lista que no responde a nada.
 */
export function useAvailableSpaces(
  consulta: { day_of_week: number; start_time: string; end_time: string; min_capacity?: number } | null,
) {
  const { accessToken, habilitado } = useSesion();

  return useQuery({
    queryKey: clavesAdmin.disponibilidad(consulta ?? {}),
    queryFn: ({ signal }) => {
      if (accessToken === null || consulta === null) {
        throw new Error("Consulta incompleta");
      }

      return consultarDisponibilidad(consulta, accessToken, signal);
    },
    enabled: habilitado && consulta !== null,
    staleTime: 0,
  });
}

/** Pone una materia en el plan, o cambia sus datos si ya estaba. */
export function useSetPlanCourse(programId: string) {
  const token = useTokenObligatorio();
  const invalidar = useInvalidarAdmin();

  return useMutation({
    mutationFn: ({
      courseId,
      ...datos
    }: {
      courseId: string;
      suggested_semester: number;
      is_mandatory: boolean;
    }) => ponerMateriaEnPlan(programId, courseId, datos, token()),
    onSuccess: invalidar,
  });
}

/** Saca una materia del plan. */
export function useRemovePlanCourse(programId: string) {
  const token = useTokenObligatorio();
  const invalidar = useInvalidarAdmin();

  return useMutation({
    mutationFn: (courseId: string) => quitarMateriaDelPlan(programId, courseId, token()),
    onSuccess: invalidar,
  });
}

/** Carga un requisito en el plan, o le cambia el tipo. */
export function useSetRequirement(programId: string) {
  const token = useTokenObligatorio();
  const invalidar = useInvalidarAdmin();

  return useMutation({
    mutationFn: ({
      courseId,
      requiredCourseId,
      requirementType,
    }: {
      courseId: string;
      requiredCourseId: string;
      requirementType: "PREREQUISITE" | "COREQUISITE";
    }) => ponerRequisito(programId, courseId, requiredCourseId, requirementType, token()),
    onSuccess: invalidar,
  });
}

/** Quita un requisito del plan. */
export function useRemoveRequirement(programId: string) {
  const token = useTokenObligatorio();
  const invalidar = useInvalidarAdmin();

  return useMutation({
    mutationFn: ({
      courseId,
      requiredCourseId,
    }: {
      courseId: string;
      requiredCourseId: string;
    }) => quitarRequisito(programId, courseId, requiredCourseId, token()),
    onSuccess: invalidar,
  });
}

/** Da de alta un espacio físico. */
export function useCreateSpace() {
  const token = useTokenObligatorio();
  const invalidar = useInvalidarAdmin();

  return useMutation({
    mutationFn: (payload: NewSpace) => crearEspacio(payload, token()),
    onSuccess: invalidar,
  });
}
