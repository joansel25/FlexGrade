/**
 * Pantalla de inicio.
 *
 * En la iteración 5.1 cumple una función concreta y temporal: demostrar que la conexión con la
 * API funciona de extremo a extremo y dejar montada la estructura visual sobre la que se
 * construyen las pantallas reales. Las tarjetas de abajo se irán sustituyendo por accesos
 * directos al catálogo, a las inscripciones y al horario en las iteraciones 5.2 a 5.5.
 */

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { useServiceStatus } from "@/features/health/useServiceStatus";

export function HomePage() {
  const { data, isPending, isError, error } = useServiceStatus();

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-ink-900 text-2xl font-semibold tracking-tight sm:text-3xl">
          Matrícula académica
        </h1>
        <p className="text-ink-600 mt-2 max-w-2xl">
          Inscribe tus materias, revisa tu horario y descarga tu comprobante. Durante la ventana
          de matrícula los cupos cambian cada segundo: esta pantalla siempre muestra la
          disponibilidad real, nunca una copia guardada.
        </p>
      </section>

      <section aria-labelledby="estado-conexion">
        <Card className="max-w-xl">
          <CardHeader>
            <CardTitle id="estado-conexion">Conexión con la API</CardTitle>
          </CardHeader>
          <CardBody>
            {isPending && <p className="text-ink-500 text-sm">Comprobando el servicio…</p>}

            {isError && (
              <div className="space-y-1">
                <p className="text-danger-700 text-sm font-medium">
                  No se pudo contactar con la API.
                </p>
                <p className="text-ink-500 text-sm">{error.message}</p>
                <p className="text-ink-500 text-sm">
                  Si estás en local, comprueba que el backend esté levantado con{" "}
                  <code className="bg-ink-100 rounded px-1 py-0.5 text-xs">docker-compose up -d</code>
                  .
                </p>
              </div>
            )}

            {data && (
              <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
                <dt className="text-ink-500">Estado</dt>
                <dd className="text-success-700 font-medium">{data.status}</dd>
                <dt className="text-ink-500">Ambiente</dt>
                <dd className="text-ink-800 font-medium">{data.environment}</dd>
                <dt className="text-ink-500">Versión</dt>
                <dd className="text-ink-800 font-medium">{data.version}</dd>
              </dl>
            )}
          </CardBody>
        </Card>
      </section>
    </div>
  );
}
