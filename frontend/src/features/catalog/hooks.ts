/**
 * Hooks del catálogo.
 *
 * Cada uno fija su propia política de frescura, y la diferencia entre ellos es la regla más
 * importante de esta iteración:
 *
 * - El **listado y el detalle** de materias se consideran frescos 30 segundos, alineados con el
 *   TTL de la caché de Redis en el backend. Pedirlos más a menudo no daría un dato más nuevo:
 *   el servidor devolvería la misma entrada cacheada.
 * - Los **grupos NUNCA se consideran frescos**, porque llevan `available_slots` dentro. Un
 *   número de cupos guardado unos segundos hace que la pantalla muestre plazas en un grupo
 *   lleno, y el estudiante descubre el error al recibir un 409 tras creer que tenía sitio.
 */

import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/features/auth/useAuth";

import {
  clavesCatalogo,
  listarMaterias,
  obtenerGrupos,
  obtenerMateria,
  obtenerPeriodoActual,
  obtenerPlanDeEstudios,
} from "@/features/catalog/api/catalog";
import type { FiltrosCatalogo } from "@/features/catalog/api/types";
import { ApiError } from "@/lib/api/errors";
import { TIEMPO_FRESCO_CATALOGO_MS, TIEMPO_FRESCO_CUPOS_MS } from "@/lib/query/queryClient";

/** Cada cuánto se refrescan solos los cupos mientras la pantalla está abierta. */
const INTERVALO_REFRESCO_CUPOS_MS = 15_000;

/** Listado paginado de materias. */
export function useCourses(filtros: FiltrosCatalogo) {
  return useQuery({
    queryKey: clavesCatalogo.materias(filtros),
    queryFn: ({ signal }) => listarMaterias(filtros, signal),
    staleTime: TIEMPO_FRESCO_CATALOGO_MS,
    // Conserva la página anterior mientras llega la siguiente. Sin esto, cada tecla escrita en
    // el buscador vaciaría la lista y la pantalla parpadearía entre resultados y vacío.
    placeholderData: (anterior) => anterior,
  });
}

/** Detalle de una materia con sus prerrequisitos. */
export function useCourseDetail(courseId: string | undefined) {
  return useQuery({
    queryKey: clavesCatalogo.materia(courseId ?? ""),
    queryFn: ({ signal }) => obtenerMateria(courseId ?? "", signal),
    enabled: Boolean(courseId),
    staleTime: TIEMPO_FRESCO_CATALOGO_MS,
  });
}

/**
 * Grupos de una materia, con sus cupos.
 *
 * Se refrescan solos cada quince segundos mientras la pantalla está abierta. Durante la ventana
 * de matrícula los cupos caen en segundos, y quien está decidiendo qué grupo inscribir necesita
 * ver el número real, no el que había cuando abrió la página.
 */
export function useCourseOfferings(courseId: string | undefined) {
  return useQuery({
    queryKey: clavesCatalogo.grupos(courseId ?? ""),
    queryFn: ({ signal }) => obtenerGrupos(courseId ?? "", signal),
    enabled: Boolean(courseId),
    staleTime: TIEMPO_FRESCO_CUPOS_MS,
    refetchInterval: INTERVALO_REFRESCO_CUPOS_MS,
    // También al volver a la pestaña: quien consultó su horario en otra ventana y regresa debe
    // ver los cupos de ahora, no los de hace tres minutos.
    refetchOnWindowFocus: true,
  });
}

/**
 * Período de matrícula vigente.
 *
 * Un `404 NO_ACTIVE_PERIOD` NO es un error: es el estado normal del sistema durante la mayor
 * parte del semestre. Se distingue del resto para que la interfaz muestre «no hay matrícula
 * abierta» en vez de un mensaje de avería.
 */
export function useCurrentPeriod() {
  return useQuery({
    queryKey: clavesCatalogo.periodoActual,
    queryFn: ({ signal }) => obtenerPeriodoActual(signal),
    // Sin caché: la respuesta lleva una cuenta atrás en segundos, y servirla de hace medio
    // minuto mostraría un reloj atrasado que salta hacia atrás al refrescarse.
    staleTime: 0,
    retry: (intentos, error) => {
      if (error instanceof ApiError && error.is("NO_ACTIVE_PERIOD")) {
        return false;
      }

      return intentos < 1;
    },
  });
}

/** Indica si el error corresponde a «no hay período de matrícula abierto». */
export function esSinPeriodoActivo(error: unknown): boolean {
  return error instanceof ApiError && error.is("NO_ACTIVE_PERIOD");
}

/**
 * Plan de estudios de la carrera del estudiante.
 *
 * Se consulta una vez y sirve para dos cosas a la vez: acotar el catálogo a las materias
 * de la carrera, y saber si una materia concreta pertenece al plan cuando se llega a su
 * ficha por un enlace directo.
 *
 * Se considera fresco cinco minutos: un plan de estudios cambia una vez por semestre, no
 * durante la ventana de matrícula.
 */
export function useStudyPlan() {
  const { accessToken, estado } = useAuth();

  return useQuery({
    queryKey: clavesCatalogo.planDeEstudios,
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        throw new Error("No hay sesión activa");
      }

      return obtenerPlanDeEstudios(accessToken, signal);
    },
    enabled: estado === "autenticado" && accessToken !== null,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}

/**
 * Conjunto de identificadores de las materias del plan del estudiante.
 *
 * Se devuelve como `Set` y no como lista porque quien lo usa pregunta «¿está esta materia
 * dentro?», no la recorre. Con un plan de sesenta materias, buscar en una lista en cada
 * tarjeta del catálogo sería trabajo repetido en cada render.
 */
export function useMyProgramCourseIds(): Set<string> {
  const { data } = useStudyPlan();

  return new Set(data?.courses.map((c) => c.id) ?? []);
}
