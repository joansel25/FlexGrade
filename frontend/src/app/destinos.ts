/**
 * Los destinos de la aplicación, en un solo sitio.
 *
 * Vive en `app/` y no en `components/` por la misma razón que `AppLayout`: no es una pieza
 * reutilizable, es la forma de ESTA aplicación.
 *
 * **Por qué una sola lista y no una por pantalla.** La barra de navegación y los accesos de la
 * pantalla de inicio muestran los mismos destinos, en el mismo orden y para los mismos roles.
 * Cuando eran dos listas separadas divergieron dos veces: al añadir «Expediente» solo se tocó
 * la barra, y —más grave— los accesos de inicio nunca filtraron por rol, así que un
 * administrador veía las cinco pantallas del estudiante y al pulsar cualquiera recibía
 * `STUDENT_PROFILE_NOT_FOUND`. La barra ya filtraba desde la Fase 9; la pantalla de inicio se
 * quedó atrás y nadie lo notó hasta una prueba manual.
 *
 * Con una sola fuente, añadir un destino es imposible de hacer a medias.
 *
 * **Qué usa cada quien.** La barra pinta `etiqueta`, que es corta porque va en una fila. La
 * pantalla de inicio pinta `titulo` y `descripcion`, que puede permitirse explicar. Son textos
 * distintos a propósito para dos sitios distintos, pero el DESTINO, el ORDEN y los ROLES son
 * los mismos y salen de aquí.
 */

import type { UserRole } from "@/features/auth/api/types";

export interface Destino {
  /** Ruta a la que lleva. */
  a: string;
  /** Texto corto, para la barra de navegación. */
  etiqueta: string;
  /** Título de la tarjeta en la pantalla de inicio. */
  titulo: string;
  /** Qué se encuentra allí. Solo lo usa la pantalla de inicio. */
  descripcion: string;
  /**
   * Quién lo ve. Vacío significa «siempre, con o sin sesión».
   *
   * Filtrar por rol y no solo por «hay sesión» dejó de ser un adorno en la Fase 9: un docente
   * tiene sesión y no tiene plan, ni catálogo que inscribir, ni materias propias. Ofrecerle
   * esos enlaces le lleva a pantallas que responden `STUDENT_PROFILE_NOT_FOUND`, y el error
   * parece del sistema y no del menú.
   */
  roles: readonly UserRole[];
}

/**
 * El orden sigue el recorrido de una matrícula: primero lo que puedo cursar en la carrera,
 * luego lo que se ofrece este período, después lo inscrito, cuándo asistir, y por último lo ya
 * cursado. Lo de cada rol va al final, porque es de pocos.
 */
// Anotado y no `as const`: con `as const`, `roles` sería una tupla distinta en cada entrada y
// el `includes` de quien filtra se estrecharía a `never`. Lo que importa aquí es que los roles
// sean válidos, no que la lista sea inmutable.
export const DESTINOS: readonly Destino[] = [
  {
    a: "/",
    etiqueta: "Inicio",
    titulo: "Inicio",
    descripcion: "El resumen de tu matrícula.",
    roles: [],
  },
  {
    a: "/plan",
    etiqueta: "Mi plan",
    titulo: "Mi plan de estudios",
    descripcion: "Qué llevas aprobado, qué puedes inscribir y qué te falta para graduarte.",
    roles: ["STUDENT"],
  },
  {
    a: "/catalogo",
    etiqueta: "Catálogo",
    titulo: "Catálogo",
    descripcion: "Las materias de tu carrera que se ofrecen este período, con sus cupos en vivo.",
    roles: ["STUDENT"],
  },
  {
    a: "/mis-materias",
    etiqueta: "Mis materias",
    titulo: "Mis materias",
    descripcion: "Lo que tienes inscrito, con la opción de cancelar y tu comprobante en PDF.",
    roles: ["STUDENT"],
  },
  {
    a: "/horario",
    etiqueta: "Horario",
    titulo: "Horario",
    descripcion: "Tus clases de la semana, ordenadas por día y hora.",
    roles: ["STUDENT"],
  },
  {
    // El expediente cierra el recorrido: es lo ya cursado, mientras que todo lo anterior mira
    // al semestre en curso.
    a: "/expediente",
    etiqueta: "Expediente",
    titulo: "Mi expediente",
    descripcion: "Todo lo que has cursado, semestre a semestre, con su nota y tu promedio.",
    roles: ["STUDENT"],
  },
  {
    a: "/docencia",
    etiqueta: "Mis grupos",
    titulo: "Mis grupos",
    descripcion: "Los grupos que dictas este período, con su lista y el registro de notas.",
    roles: ["PROFESSOR"],
  },
  {
    a: "/admin",
    etiqueta: "Administración",
    titulo: "Administración",
    descripcion:
      "Ventanas de matrícula, catálogo, grupos, planes, espacios y reportes de Registro " +
      "Académico.",
    roles: ["ADMIN"],
  },
];

/**
 * Los destinos que le corresponden a un rol.
 *
 * `rol` en `null` es la sesión todavía sin resolver —la ventana entre el refresco y su
 * respuesta—: ahí no se pinta nada de rol, porque aparecer y desaparecer se lee como un
 * parpadeo.
 */
export function destinosDe(rol: UserRole | null): Destino[] {
  return DESTINOS.filter(
    (destino) => destino.roles.length === 0 || (rol !== null && destino.roles.includes(rol)),
  );
}
