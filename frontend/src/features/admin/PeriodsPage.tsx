/**
 * Ventanas de matrícula: abrirlas y activarlas.
 *
 * ACTIVAR ES LA OPERACIÓN MÁS DELICADA DE TODA LA ADMINISTRACIÓN, y la pantalla lo trata como
 * tal. Cambia a la vez lo que ven todos los estudiantes: la que estuviera activa se cierra —el
 * índice único parcial de PostgreSQL garantiza que nunca haya dos— y la nueva empieza a admitir
 * inscripciones. Por eso pide confirmación nombrando la consecuencia, y no un «¿estás seguro?»
 * que nadie lee.
 *
 * Crear y activar están separados a propósito, igual que en la API: una ventana nace inactiva.
 * Preparar el semestre siguiente sin cerrar el actual es el caso normal, y unir las dos
 * operaciones lo haría imposible.
 *
 * Las fechas se escriben en HORA LOCAL y viajan en UTC. El `datetime-local` del navegador da un
 * texto sin zona; convertirlo aquí evita que una ventana abierta «a las 8:00» se abra a las 3 de
 * la madrugada en el servidor.
 */

import { useState } from "react";

import { Alert, Button, Card, CardBody, CardHeader, CardTitle, EmptyState, Skeleton, TextField } from "@/components/ui";
import type { EnrollmentPeriod } from "@/features/admin/api/types";
import { useActivatePeriod, useCreatePeriod, usePeriods } from "@/features/admin/hooks";
import { mensajeDeAdmin } from "@/features/admin/mensajes";

export function PeriodsPage() {
  const periodos = usePeriods();

  return (
    <div className="space-y-6">
      <FormularioDePeriodo />

      <section aria-labelledby="ventanas" className="space-y-3">
        <h2 id="ventanas" className="text-ink-900 text-lg font-semibold">
          Ventanas de matrícula
        </h2>

        {periodos.isPending && <ListaCargando />}

        {periodos.isError && (
          <Alert tono="error" titulo="No se pudieron cargar las ventanas">
            {mensajeDeAdmin(periodos.error).detalle}
          </Alert>
        )}

        {periodos.data && periodos.data.items.length === 0 && (
          <EmptyState
            titulo="Todavía no hay ninguna ventana"
            descripcion="Crea la primera con el formulario de arriba. Nacerá inactiva."
          />
        )}

        {periodos.data && periodos.data.items.length > 0 && (
          <ul className="space-y-2">
            {periodos.data.items.map((periodo) => (
              <li key={periodo.id}>
                <FilaDePeriodo periodo={periodo} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function FormularioDePeriodo() {
  const [code, setCode] = useState("");
  const [academicPeriod, setAcademicPeriod] = useState("");
  const [name, setName] = useState("");
  const [startsAt, setStartsAt] = useState("");
  const [endsAt, setEndsAt] = useState("");

  const creacion = useCreatePeriod();
  const fallo = creacion.isError ? mensajeDeAdmin(creacion.error) : null;
  const completo = code && academicPeriod && name && startsAt && endsAt;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Abrir una ventana de matrícula</CardTitle>
      </CardHeader>
      <CardBody>
        <form
          className="space-y-4"
          onSubmit={(evento) => {
            evento.preventDefault();
            creacion.mutate(
              {
                code: code.trim(),
                academic_period: academicPeriod.trim(),
                name: name.trim(),
                // `toISOString()` convierte la hora local a UTC, que es lo que la API espera.
                starts_at: new Date(startsAt).toISOString(),
                ends_at: new Date(endsAt).toISOString(),
              },
              {
                onSuccess: () => {
                  setCode("");
                  setAcademicPeriod("");
                  setName("");
                  setStartsAt("");
                  setEndsAt("");
                },
              },
            );
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              etiqueta="Código"
              ayuda="Único. Por ejemplo 2025-2-V1 para la primera vuelta."
              value={code}
              onChange={(e) => setCode(e.target.value)}
              maxLength={20}
              required
            />
            <TextField
              etiqueta="Semestre"
              ayuda="El período académico: 2025-2."
              value={academicPeriod}
              onChange={(e) => setAcademicPeriod(e.target.value)}
              maxLength={20}
              required
            />
          </div>

          <TextField
            etiqueta="Nombre"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={150}
            required
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              etiqueta="Apertura"
              ayuda="En tu hora local; se guarda en UTC."
              type="datetime-local"
              value={startsAt}
              onChange={(e) => setStartsAt(e.target.value)}
              required
            />
            <TextField
              etiqueta="Cierre"
              type="datetime-local"
              value={endsAt}
              onChange={(e) => setEndsAt(e.target.value)}
              required
            />
          </div>

          {fallo && (
            <Alert tono="error" titulo={fallo.titulo}>
              {fallo.detalle}
            </Alert>
          )}

          {creacion.isSuccess && (
            <Alert tono="exito" titulo="Ventana creada">
              Nace inactiva. Actívala abajo cuando quieras que empiece a admitir inscripciones.
            </Alert>
          )}

          <Button type="submit" cargando={creacion.isPending} disabled={!completo}>
            Crear ventana
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

function FilaDePeriodo({ periodo }: { periodo: EnrollmentPeriod }) {
  const [confirmando, setConfirmando] = useState(false);
  const activacion = useActivatePeriod();

  const fallo = activacion.isError ? mensajeDeAdmin(activacion.error) : null;

  return (
    <Card className={periodo.is_active ? "border-success-600/40" : undefined}>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-ink-900 text-sm font-medium">
              <span className="text-brand-700 font-mono text-xs">{periodo.code}</span>{" "}
              {periodo.name}
            </p>
            <p className="text-ink-500 text-xs">
              {periodo.academic_period} ·{" "}
              {new Date(periodo.starts_at).toLocaleString("es-CO")} —{" "}
              {new Date(periodo.ends_at).toLocaleString("es-CO")}
            </p>
          </div>

          {periodo.is_active ? (
            <span className="bg-success-50 border-success-600/25 text-success-700 rounded-full border px-2 py-0.5 text-xs font-medium">
              Activa
            </span>
          ) : confirmando ? (
            <div className="space-y-2 sm:text-right">
              <p className="text-ink-700 max-w-xs text-sm">
                {/* La consecuencia real, no un «¿estás seguro?»: esto cambia a la vez lo que
                    ven todos los estudiantes. */}
                Al activarla se cerrará la ventana que esté abierta ahora, y los estudiantes
                pasarán a matricularse en esta.
              </p>
              <div className="flex gap-2 sm:justify-end">
                <Button
                  variante="secundario"
                  tamano="sm"
                  onClick={() => setConfirmando(false)}
                  disabled={activacion.isPending}
                >
                  Cancelar
                </Button>
                <Button
                  tamano="sm"
                  cargando={activacion.isPending}
                  onClick={() => activacion.mutate(periodo.id)}
                >
                  Sí, activar
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variante="secundario"
              tamano="sm"
              onClick={() => setConfirmando(true)}
              aria-label={`Activar la ventana ${periodo.code}`}
            >
              Activar
            </Button>
          )}
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
    <ul className="space-y-2" role="status" aria-live="polite">
      <span className="sr-only">Cargando las ventanas…</span>
      {Array.from({ length: 2 }, (_, indice) => (
        <li key={indice} className="rounded-card border-ink-200 space-y-2 border bg-white p-5">
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-3 w-48" />
        </li>
      ))}
    </ul>
  );
}
