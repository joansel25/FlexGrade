/**
 * Estado del servicio, para el panel de administración.
 *
 * **Vuelve donde tiene sentido operativo, y solo ahí.** La iteración 6.4 lo retiró de la
 * interfaz del estudiante por una razón concreta: no puede hacer nada con un punto rojo, y ver
 * el ambiente o un número de versión en la primera pantalla de su matrícula solo genera
 * desconfianza. Quien administra sí puede hacer algo: si la API deja de responder en plena
 * ventana de matrícula, es lo primero que necesita saber, antes de que empiecen a llegar
 * llamadas preguntando por qué nadie puede inscribirse.
 *
 * Muestra el AMBIENTE además del estado, y eso tampoco es adorno aquí: distinguir producción de
 * pruebas evita el error clásico de tocar cupos reales creyendo estar en un entorno de ensayo.
 */

import { Alert, Card, CardBody, CardHeader, CardTitle, StatusDot } from "@/components/ui";
import type { Estado } from "@/components/ui";
import { useServiceStatus } from "@/features/health/useServiceStatus";

export function ServiceStatusCard() {
  const { data, isPending, isError, error } = useServiceStatus();

  const estado: Estado = isPending ? "desconocido" : isError ? "error" : "ok";

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Estado del servicio</CardTitle>
      </CardHeader>
      <CardBody className="space-y-3">
        <StatusDot estado={estado} pulsando={isPending}>
          {isPending ? "Comprobando…" : isError ? "Sin conexión" : "En línea"}
        </StatusDot>

        {isError && (
          <Alert tono="error" titulo="La API no responde">
            {/* El mensaje del servidor, no un texto genérico: aquí lo lee alguien que puede
                actuar sobre la causa. */}
            {error.message}
          </Alert>
        )}

        {data && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
            <dt className="text-ink-500">Ambiente</dt>
            <dd className="text-ink-800 font-medium">{data.environment}</dd>
            <dt className="text-ink-500">Versión</dt>
            <dd className="text-ink-800 font-medium">{data.version}</dd>
          </dl>
        )}
      </CardBody>
    </Card>
  );
}
