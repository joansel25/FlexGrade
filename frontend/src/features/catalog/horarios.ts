/**
 * Formato de las franjas horarias.
 *
 * Vive aparte porque lo usan el catálogo, el detalle del grupo y —en la iteración 5.4— el
 * horario del estudiante. Que las tres pantallas escriban «Lun 08:00–10:00» exactamente igual
 * no es cosmética: leer el mismo dato con tres formatos distintos obliga a releer.
 */

import type { ScheduleBlock } from "@/features/catalog/api/types";

/** Nombres cortos de los días, indexados por el valor ISO 8601 (1 = lunes). */
const DIAS: Record<number, string> = {
  1: "Lun",
  2: "Mar",
  3: "Mié",
  4: "Jue",
  5: "Vie",
  6: "Sáb",
  7: "Dom",
};

/** Nombres completos, para los lectores de pantalla y los textos alternativos. */
const DIAS_COMPLETOS: Record<number, string> = {
  1: "lunes",
  2: "martes",
  3: "miércoles",
  4: "jueves",
  5: "viernes",
  6: "sábado",
  7: "domingo",
};

/** Nombre corto del día (`Lun`), o el número si llegara uno fuera de rango. */
export function nombreDeDia(dia: number): string {
  return DIAS[dia] ?? `Día ${dia}`;
}

/** Nombre completo del día, en minúsculas. */
export function nombreCompletoDeDia(dia: number): string {
  return DIAS_COMPLETOS[dia] ?? `día ${dia}`;
}

/**
 * Recorta la hora a `HH:MM`.
 *
 * La API puede devolver `08:00:00`: los segundos son ruido en un horario académico, donde
 * ninguna clase empieza a y treinta segundos.
 */
export function formatearHora(hora: string): string {
  return hora.slice(0, 5);
}

/** Franja completa en formato corto: `Lun 08:00–10:00`. */
export function formatearFranja(franja: ScheduleBlock): string {
  // Raya (–) y no guion: es el signo tipográfico correcto para un intervalo.
  return `${nombreDeDia(franja.day_of_week)} ${formatearHora(franja.start_time)}–${formatearHora(franja.end_time)}`;
}

/** Franja en texto corrido, para quien la escucha en vez de leerla. */
export function describirFranja(franja: ScheduleBlock): string {
  const aula = franja.classroom ? `, aula ${franja.classroom}` : "";

  return (
    `${nombreCompletoDeDia(franja.day_of_week)} de ${formatearHora(franja.start_time)} ` +
    `a ${formatearHora(franja.end_time)}${aula}`
  );
}

/**
 * Ordena las franjas por día y hora.
 *
 * El backend ya las devuelve ordenadas dentro de cada grupo, pero esta función se aplica
 * igualmente: es barata y deja la pantalla correcta aunque el orden del servidor cambie.
 */
export function ordenarFranjas(franjas: ScheduleBlock[]): ScheduleBlock[] {
  return [...franjas].sort(
    (a, b) => a.day_of_week - b.day_of_week || a.start_time.localeCompare(b.start_time),
  );
}
