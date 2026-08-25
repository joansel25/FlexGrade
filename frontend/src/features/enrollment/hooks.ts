/**
 * Hooks del flujo de inscripción.
 *
 * Aquí se concentra la regla que sostiene toda la iteración: **después de inscribir o cancelar,
 * lo que el estudiante ve tiene que dejar de estar desactualizado inmediatamente.** Tres cosas
 * cambian a la vez con cada operación —sus materias, su horario y los cupos del grupo—, y si
 * alguna se queda atrás, la pantalla miente en el peor momento.
 *
 * No se usan actualizaciones optimistas. Sería tentador pintar la inscripción antes de que el
 * servidor responda, pero en este dominio es exactamente lo que no se debe hacer: el resultado
 * de inscribir depende de una carrera por el último cupo que solo PostgreSQL puede resolver.
 * Mostrar «inscrito» y retirarlo medio segundo después es peor que esperar.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/useAuth";
import { clavesCatalogo } from "@/features/catalog/api/catalog";
import {
  cancelar,
  clavesInscripcion,
  inscribir,
  listarInscripciones,
  obtenerHorario,
} from "@/features/enrollment/api/enrollment";
import { TIEMPO_FRESCO_CUPOS_MS } from "@/lib/query/queryClient";

/**
 * Inscripciones activas del estudiante.
 *
 * Sin caché: es la lista desde la que se cancela, y servirla desactualizada ofrecería cancelar
 * algo que ya no existe. Además cada elemento lleva su grupo, cuyos cupos cambian constantemente.
 */
export function useMyEnrollments() {
  const { accessToken, estado } = useAuth();

  return useQuery({
    queryKey: clavesInscripcion.mias,
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return listarInscripciones(accessToken, signal);
    },
    enabled: estado === "autenticado" && accessToken !== null,
    staleTime: TIEMPO_FRESCO_CUPOS_MS,
  });
}

/** Horario armado del estudiante. */
export function useMySchedule() {
  const { accessToken, estado } = useAuth();

  return useQuery({
    queryKey: clavesInscripcion.horario,
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return obtenerHorario(accessToken, signal);
    },
    enabled: estado === "autenticado" && accessToken !== null,
    staleTime: TIEMPO_FRESCO_CUPOS_MS,
  });
}

/**
 * Invalida todo lo que una inscripción o una cancelación deja obsoleto.
 *
 * Se invalidan **las tres cosas juntas** y en un solo sitio: las materias del estudiante, su
 * horario y los grupos del catálogo —que llevan `available_slots` y acaban de cambiar—.
 * Repartir esta lista por cada pantalla es la forma segura de que alguna se olvide, y el
 * síntoma sería un cupo que no baja tras inscribir.
 */
function useInvalidarTrasOperar() {
  const queryClient = useQueryClient();

  return () => {
    // `void` porque no se espera: la pantalla ya puede reaccionar al éxito mientras las
    // consultas se refrescan por detrás.
    void queryClient.invalidateQueries({ queryKey: clavesInscripcion.todo });
    void queryClient.invalidateQueries({ queryKey: clavesCatalogo.todo });
  };
}

/** Inscribe al estudiante en un grupo. */
export function useEnroll() {
  const { accessToken } = useAuth();
  const invalidar = useInvalidarTrasOperar();

  return useMutation({
    mutationFn: (courseOfferingId: string) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return inscribir(courseOfferingId, accessToken);
    },
    onSuccess: invalidar,
    // También al fallar: un `COURSE_CAPACITY_EXCEEDED` significa que el grupo se llenó, así
    // que los cupos en pantalla ya no valen. Refrescarlos hace que el mensaje «elige otro
    // grupo» venga acompañado de los números correctos.
    onError: invalidar,
  });
}

/** Cancela una inscripción y libera el cupo. */
export function useCancelEnrollment() {
  const { accessToken } = useAuth();
  const invalidar = useInvalidarTrasOperar();

  return useMutation({
    mutationFn: (enrollmentId: string) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return cancelar(enrollmentId, accessToken);
    },
    onSuccess: invalidar,
    onError: invalidar,
  });
}
