/**
 * Disponibilidad de cupos de un grupo.
 *
 * Es el dato más importante de toda la pantalla y el que más rápido cambia, así que se comunica
 * por tres vías a la vez: **color**, **texto** y **número**. Confiar solo en el color dejaría
 * fuera a quien no distingue verde de rojo —entre el 5 % y el 8 % de los hombres— y a
 * cualquiera mirando el móvil bajo el sol.
 *
 * Los umbrales no son arbitrarios: por debajo de cinco plazas, en una ventana con miles de
 * personas conectadas, el grupo puede llenarse mientras se decide. Marcarlo como «últimos
 * cupos» es información útil, no alarmismo.
 */

import { StatusDot, type Estado } from "@/components/ui";

/** A partir de cuántas plazas libres se considera que el grupo va justo. */
const UMBRAL_ULTIMOS_CUPOS = 5;

interface CapacityBadgeProps {
  disponibles: number;
  total: number;
}

export function CapacityBadge({ disponibles, total }: CapacityBadgeProps) {
  const { estado, texto } = describir(disponibles, total);

  return <StatusDot estado={estado}>{texto}</StatusDot>;
}

function describir(disponibles: number, total: number): { estado: Estado; texto: string } {
  if (disponibles <= 0) {
    return { estado: "error", texto: "Sin cupos" };
  }

  if (disponibles <= UMBRAL_ULTIMOS_CUPOS) {
    // El singular importa: «1 cupos» se lee como un descuido y resta confianza justo en el
    // dato que la persona está mirando para decidir.
    return {
      estado: "advertencia",
      texto: disponibles === 1 ? "Último cupo" : `Quedan ${disponibles} cupos`,
    };
  }

  return { estado: "ok", texto: `${disponibles} de ${total} cupos` };
}
