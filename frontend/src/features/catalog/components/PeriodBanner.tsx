/**
 * Estado de la ventana de matrícula.
 *
 * Responde la pregunta que trae a todo el mundo a la aplicación: «¿puedo matricular ahora?».
 * La respuesta tiene tres estados distintos y confundirlos genera reclamos:
 *
 * - **Abierta**: se puede inscribir, y se muestra cuánto queda.
 * - **Activada pero fuera de fechas**: hay período, pero todavía no empieza o ya cerró. Es la
 *   diferencia entre `is_active` e `is_open` del contrato, y es la que permite decir «abre el
 *   martes» en vez de dejar un botón que fallará con un 409.
 * - **Sin período**: el estado normal durante la mayor parte del semestre. NO es un error.
 */

import { Alert } from "@/components/ui";
import { esSinPeriodoActivo, useCurrentPeriod } from "@/features/catalog/hooks";
import { formatearTiempoRestante } from "@/features/catalog/tiempoRestante";

export function PeriodBanner() {
  const { data: periodo, isPending, isError, error } = useCurrentPeriod();

  if (isPending) {
    return null;
  }

  if (isError) {
    if (esSinPeriodoActivo(error)) {
      return (
        <Alert tono="info" titulo="No hay matrícula abierta">
          Puedes consultar el catálogo, pero las inscripciones no están habilitadas en este
          momento.
        </Alert>
      );
    }

    // Un fallo real de la API no se disfraza de «no hay período»: son cosas distintas y la
    // segunda haría creer que el sistema funciona cuando no responde.
    return null;
  }

  if (!periodo.is_open) {
    return (
      <Alert tono="advertencia" titulo={periodo.name}>
        La ventana de matrícula no está abierta en este momento. Consulta el catálogo mientras
        tanto.
      </Alert>
    );
  }

  return (
    <Alert tono="exito" titulo={`Matrícula abierta · ${periodo.name}`}>
      Cierra en {formatearTiempoRestante(periodo.time_remaining_seconds)}.
    </Alert>
  );
}
