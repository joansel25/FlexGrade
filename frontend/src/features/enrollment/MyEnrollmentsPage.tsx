/**
 * Mis materias: lo inscrito en el período vigente, con la opción de cancelar.
 *
 * Cancelar es destructivo y libera un cupo que otra persona puede tomar en segundos, así que
 * pide confirmación en dos pasos dentro de la propia fila. No se usa un `window.confirm`: no se
 * puede dar estilo, no se puede explicar bien la consecuencia y bloquea el navegador entero.
 *
 * Y puede arrastrar más de una materia. Las unidas por correquisitos mutuos —la teoría y su
 * laboratorio— se abandonan como un bloque, y el servidor responde con la lista de lo que
 * canceló. Ese aviso se pinta en la PÁGINA y no en la fila: la fila que se acaba de cancelar
 * desaparece de la lista en cuanto llega la respuesta, y con ella se iría el mensaje que
 * explica lo ocurrido justo antes de poder leerse.
 */

import { useState } from "react";
import { Link } from "react-router-dom";

import { Alert, Button, Card, CardBody, EmptyState, Skeleton } from "@/components/ui";
import { ScheduleList } from "@/features/catalog/components/ScheduleList";
import { esSinPeriodoActivo } from "@/features/catalog/hooks";
import type { CancelledEnrollment, StudentEnrollment } from "@/features/enrollment/api/types";
import { ReceiptButton } from "@/features/enrollment/components/ReceiptButton";
import { useCancelEnrollment, useMyEnrollments } from "@/features/enrollment/hooks";
import { mensajeDeCancelacion } from "@/features/enrollment/mensajes";

export function MyEnrollmentsPage() {
  const { data, isPending, isError, error } = useMyEnrollments();

  // Lo que arrastró la última cancelación. Solo se anuncia cuando fue más de una materia:
  // decir «cancelaste MAT101» después de pulsar «Cancelar» en MAT101 es ruido.
  const [arrastradas, setArrastradas] = useState<CancelledEnrollment[]>([]);

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-ink-900 text-2xl font-semibold tracking-tight sm:text-3xl">
            Mis materias
          </h1>
          {data && (
            <p className="text-ink-600 mt-2">
              {data.items.length}{" "}
              {data.items.length === 1 ? "materia inscrita" : "materias inscritas"}
              {" · "}
              {data.total_credits} {data.total_credits === 1 ? "crédito" : "créditos"}
              {" · "}
              período {data.period}
            </p>
          )}
        </div>

        {/* Se ofrece aunque no haya nada inscrito: un comprobante vacío certifica ese estado,
            y a veces hay que demostrarlo. */}
        {data && <ReceiptButton />}
      </header>

      {arrastradas.length > 1 && (
        <Alert tono="info" titulo="Se canceló el bloque completo">
          {arrastradas.map((c) => `${c.course_code} — ${c.course_name}`).join(" y ")} se cursan
          juntas, así que se cancelaron las dos. Volver a inscribir una sin la otra tampoco es
          posible.
        </Alert>
      )}

      {isPending && <ListaCargando />}

      {isError && !esSinPeriodoActivo(error) && (
        <Alert tono="error" titulo="No se pudieron cargar tus materias">
          {error.message}
        </Alert>
      )}

      {isError && esSinPeriodoActivo(error) && (
        <Alert tono="info" titulo="No hay matrícula abierta">
          Tus materias aparecerán aquí cuando se abra la ventana de matrícula del período.
        </Alert>
      )}

      {data && data.items.length === 0 && (
        <EmptyState
          titulo="Todavía no has inscrito ninguna materia"
          descripcion="Busca en el catálogo la materia que quieras cursar y elige uno de sus grupos."
          accion={
            <Link
              to="/catalogo"
              className="bg-brand-600 hover:bg-brand-700 inline-flex h-10 items-center rounded-lg px-4 text-sm font-medium text-white transition-colors"
            >
              Ir al catálogo
            </Link>
          }
        />
      )}

      {data && data.items.length > 0 && (
        <ul className="space-y-3">
          {data.items.map((inscripcion) => (
            <li key={inscripcion.id}>
              <FilaDeInscripcion inscripcion={inscripcion} onCancelada={setArrastradas} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FilaDeInscripcion({
  inscripcion,
  onCancelada,
}: {
  inscripcion: StudentEnrollment;
  onCancelada: (canceladas: CancelledEnrollment[]) => void;
}) {
  const [confirmando, setConfirmando] = useState(false);
  const cancelacion = useCancelEnrollment();

  const fallo = cancelacion.isError ? mensajeDeCancelacion(cancelacion.error) : null;
  const pendientes = inscripcion.pending_corequisites;

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-baseline gap-2">
              <Link
                to={`/catalogo/${inscripcion.course_id}`}
                className="text-brand-700 hover:text-brand-800 font-mono text-xs font-semibold"
              >
                {inscripcion.course_code}
              </Link>
              <h2 className="text-ink-900 text-base font-semibold">{inscripcion.course_name}</h2>
              <span className="text-ink-500 text-xs">
                Grupo {inscripcion.group_number} · {inscripcion.credits}{" "}
                {inscripcion.credits === 1 ? "crédito" : "créditos"}
              </span>
            </div>

            <p className="text-ink-600 text-sm">
              {inscripcion.professor ?? "Docente por asignar"}
            </p>

            <ScheduleList franjas={inscripcion.schedule} />

            {pendientes.length > 0 && (
              <Alert tono="advertencia" titulo="Te falta inscribir una materia que va con esta">
                {/* El servidor calcula qué falta con la misma regla que decide si la
                    inscripción se acepta. Repetirla aquí garantizaría que un día discrepen. */}
                Esta materia se cursa junto a {pendientes.join(", ")}. Mientras no la inscribas,
                tu matrícula está incompleta.{" "}
                <Link to="/catalogo" className="font-medium underline">
                  Buscarla en el catálogo
                </Link>
              </Alert>
            )}
          </div>

          <div className="shrink-0">
            {confirmando ? (
              <div className="space-y-2 sm:text-right">
                <p className="text-ink-700 max-w-xs text-sm">
                  {/* Se nombra la consecuencia real, no un «¿estás seguro?» genérico: durante
                      la matrícula el cupo liberado puede desaparecer en segundos. */}
                  Al cancelar liberas tu cupo, y otra persona puede tomarlo de inmediato.
                </p>
                <div className="flex gap-2 sm:justify-end">
                  <Button
                    variante="secundario"
                    tamano="sm"
                    onClick={() => setConfirmando(false)}
                    disabled={cancelacion.isPending}
                  >
                    Conservar
                  </Button>
                  <Button
                    variante="peligro"
                    tamano="sm"
                    cargando={cancelacion.isPending}
                    onClick={() =>
                      cancelacion.mutate(inscripcion.id, {
                        onSuccess: (resultado) => onCancelada(resultado.cancelled),
                      })
                    }
                  >
                    Sí, cancelar
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variante="secundario"
                tamano="sm"
                onClick={() => setConfirmando(true)}
                aria-label={`Cancelar ${inscripcion.course_code} grupo ${inscripcion.group_number}`}
              >
                Cancelar
              </Button>
            )}
          </div>
        </div>

        {fallo && (
          <Alert tono="error" titulo={fallo.titulo}>
            {fallo.detalle}
          </Alert>
        )}
      </CardBody>
    </Card>
  );
}

function ListaCargando() {
  return (
    <ul className="space-y-3" role="status" aria-live="polite">
      <span className="sr-only">Cargando tus materias…</span>
      {Array.from({ length: 3 }, (_, indice) => (
        <li key={indice} className="rounded-card border-ink-200 space-y-3 border bg-white p-5">
          <Skeleton className="h-5 w-64" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-6 w-48" />
        </li>
      ))}
    </ul>
  );
}
