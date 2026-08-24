/**
 * Indicador del estado de la API en la cabecera.
 *
 * Lo que muestra es deliberadamente escueto: si todo va bien, un punto verde y el ambiente
 * (`dev`, `staging`, `prod`); si la API no responde, un aviso legible. Nunca un código de error
 * crudo: el estudiante no puede hacer nada con un 502, y ver el ambiente es lo que evita
 * confundir producción con pruebas durante una demostración.
 */

import { StatusDot, type Estado } from "@/components/ui";
import { useServiceStatus } from "@/features/health/useServiceStatus";

export function ServiceStatus() {
  const { data, isPending, isError } = useServiceStatus();

  const { estado, texto }: { estado: Estado; texto: string } = isPending
    ? { estado: "desconocido", texto: "Comprobando…" }
    : isError
      ? { estado: "error", texto: "Sin conexión" }
      : { estado: "ok", texto: `En línea · ${data.environment}` };

  return (
    <StatusDot
      estado={estado}
      pulsando={isPending}
      // `title` da el detalle completo a quien pase el ratón, sin ocupar espacio en la barra.
      className="hidden sm:inline-flex"
    >
      {texto}
    </StatusDot>
  );
}
