/**
 * Horario de un grupo.
 *
 * Se pinta como lista y no como texto seguido: son datos separados —cada franja es una clase a
 * la que hay que ir— y una lista permite a un lector de pantalla anunciar cuántas hay y
 * recorrerlas una a una.
 */

import type { ScheduleBlock } from "@/features/catalog/api/types";
import { describirFranja, formatearFranja, ordenarFranjas } from "@/features/catalog/horarios";

export function ScheduleList({ franjas }: { franjas: ScheduleBlock[] }) {
  if (franjas.length === 0) {
    // Un grupo puede publicarse antes de tener horario asignado. Decirlo es mejor que dejar un
    // hueco que se lee como un error de carga.
    return <p className="text-ink-500 text-sm">Horario por definir</p>;
  }

  return (
    <ul className="flex flex-wrap gap-1.5">
      {ordenarFranjas(franjas).map((franja, indice) => (
        <li
          // El índice como clave es correcto AQUÍ: la lista es de solo lectura, no se
          // reordena ni se filtra, y las franjas no tienen identidad propia en el dominio
          // (son value objects). En una lista editable sería un error.
          key={`${franja.day_of_week}-${franja.start_time}-${indice}`}
          className="bg-ink-100 text-ink-700 rounded px-2 py-1 text-xs font-medium"
        >
          {/* El texto visible es compacto; el accesible, completo. */}
          <span aria-hidden="true">{formatearFranja(franja)}</span>
          <span className="sr-only">{describirFranja(franja)}</span>
          {franja.classroom && (
            <span className="text-ink-500 ml-1.5 font-normal" aria-hidden="true">
              {franja.classroom}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
