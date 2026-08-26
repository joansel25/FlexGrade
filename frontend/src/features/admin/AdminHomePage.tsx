/**
 * Panel de administración: lo que hay que vigilar mientras la matrícula ocurre.
 *
 * No es un resumen bonito, es una lista de decisiones pendientes. Las tres cifras de arriba
 * dicen si la matrícula avanza; la tabla de abajo dice sobre QUÉ grupos hay que decidir ahora
 * —ampliar el cupo o abrir otro grupo— y por eso llega ordenada del más lleno al más vacío.
 *
 * **Todo se refresca solo cada treinta segundos y nada se cachea.** Durante la ventana de
 * matrícula estas cifras cambian cada segundo, y un panel que muestra números de hace un minuto
 * con aspecto de actuales lleva a decidir sobre un cupo que ya no existe. Es la misma razón por
 * la que el backend calcula los reportes en vivo en vez de guardarlos.
 */

import { Alert, Card, CardBody, EmptyState, Skeleton } from "@/components/ui";
import type { OfferingOccupancy } from "@/features/admin/api/types";
import { useEnrollmentReport, useOccupancyReport } from "@/features/admin/hooks";
import { esSinPeriodoActivo } from "@/features/catalog/hooks";
import { ServiceStatusCard } from "@/features/health/components/ServiceStatusCard";
import { cn } from "@/lib/cn";

/** A partir de qué ocupación un grupo pasa a ser algo sobre lo que hay que decidir. */
const UMBRAL_CRITICO = 90;

export function AdminHomePage() {
  const inscripciones = useEnrollmentReport();
  const ocupacion = useOccupancyReport();

  const sinPeriodo =
    esSinPeriodoActivo(inscripciones.error) || esSinPeriodoActivo(ocupacion.error);

  if (sinPeriodo) {
    return (
      <Alert tono="info" titulo="No hay ventana de matrícula abierta">
        El panel muestra lo que ocurre durante la matrícula. Cuando se active un período,
        aparecerán aquí las cifras y los grupos a punto de llenarse.
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="cifras" className="space-y-3">
        <h2 id="cifras" className="text-ink-900 text-lg font-semibold">
          Cómo va la matrícula
        </h2>

        {inscripciones.isPending && <CifrasCargando />}

        {inscripciones.isError && (
          <Alert tono="error" titulo="No se pudieron cargar las cifras">
            {inscripciones.error.message}
          </Alert>
        )}

        {inscripciones.data && (
          <>
            <dl className="grid gap-3 sm:grid-cols-3">
              <Cifra
                etiqueta="Inscripciones activas"
                valor={inscripciones.data.totals.total_enrollments}
              />
              <Cifra
                etiqueta="Estudiantes distintos"
                valor={inscripciones.data.totals.unique_students}
              />
              <Cifra
                etiqueta="Grupos con inscritos"
                valor={inscripciones.data.totals.active_offerings}
              />
            </dl>
            <p className="text-ink-500 text-xs">
              Período {inscripciones.data.period_code} · calculado{" "}
              {new Date(inscripciones.data.generated_at).toLocaleTimeString("es-CO")} · se
              actualiza solo
            </p>
          </>
        )}
      </section>

      <section aria-labelledby="mas-llenos" className="space-y-3">
        <h2 id="mas-llenos" className="text-ink-900 text-lg font-semibold">
          Grupos a punto de llenarse
        </h2>

        {ocupacion.isPending && <TablaCargando />}

        {ocupacion.isError && (
          <Alert tono="error" titulo="No se pudo cargar la ocupación">
            {ocupacion.error.message}
          </Alert>
        )}

        {ocupacion.data && ocupacion.data.offerings.length === 0 && (
          <EmptyState
            titulo="Todavía no hay grupos con inscritos"
            descripcion="Aparecerán aquí en cuanto empiecen las inscripciones del período."
          />
        )}

        {ocupacion.data && ocupacion.data.offerings.length > 0 && (
          <ul className="space-y-2">
            {ocupacion.data.offerings.map((grupo) => (
              <li key={grupo.offering_id}>
                <FilaDeOcupacion grupo={grupo} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* El estado del servicio vuelve aquí, y solo aquí. La iteración 6.4 lo quitó de la
          interfaz del estudiante porque no puede hacer nada con él; quien administra sí: si la
          API no responde durante la ventana de matrícula, es lo primero que hay que saber. */}
      <ServiceStatusCard />
    </div>
  );
}

function Cifra({ etiqueta, valor }: { etiqueta: string; valor: number }) {
  return (
    <Card>
      <CardBody>
        <dt className="text-ink-500 text-sm">{etiqueta}</dt>
        <dd className="text-ink-900 mt-1 text-3xl font-semibold tabular-nums">{valor}</dd>
      </CardBody>
    </Card>
  );
}

function FilaDeOcupacion({ grupo }: { grupo: OfferingOccupancy }) {
  const critico = grupo.occupancy_rate >= UMBRAL_CRITICO;

  return (
    <Card className={critico ? "border-warning-600/40" : undefined}>
      <CardBody className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-ink-900 text-sm font-medium">
            <span className="text-brand-700 font-mono text-xs">{grupo.course_code}</span>{" "}
            {grupo.course_name} · Grupo {grupo.group_number}
          </p>
          <p className="text-ink-500 text-xs">
            {grupo.enrolled_count} / {grupo.total_capacity} inscritos ·{" "}
            {/* Se dice cuántos QUEDAN y no solo el porcentaje: «3 cupos» decide más rápido
                que «92,5 %». */}
            {grupo.available_slots}{" "}
            {grupo.available_slots === 1 ? "cupo libre" : "cupos libres"}
          </p>
        </div>

        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-xs font-medium tabular-nums",
            critico
              ? "bg-warning-50 border-warning-600/25 text-warning-700"
              : "border-ink-200 text-ink-600 bg-white",
          )}
        >
          {grupo.occupancy_rate.toFixed(1)} %
        </span>
      </CardBody>
    </Card>
  );
}

function CifrasCargando() {
  return (
    <div className="grid gap-3 sm:grid-cols-3" role="status" aria-live="polite">
      <span className="sr-only">Cargando las cifras…</span>
      {Array.from({ length: 3 }, (_, indice) => (
        <div key={indice} className="rounded-card border-ink-200 space-y-2 border bg-white p-5">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-8 w-16" />
        </div>
      ))}
    </div>
  );
}

function TablaCargando() {
  return (
    <ul className="space-y-2" role="status" aria-live="polite">
      <span className="sr-only">Cargando la ocupación…</span>
      {Array.from({ length: 3 }, (_, indice) => (
        <li key={indice} className="rounded-card border-ink-200 space-y-2 border bg-white p-5">
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-3 w-40" />
        </li>
      ))}
    </ul>
  );
}
