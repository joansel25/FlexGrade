/**
 * La lista de un grupo: quién está inscrito y qué nota lleva.
 *
 * **Cada fila se guarda por separado, no hay un «guardar todo».** Calificar cuarenta personas
 * es un trabajo que se hace a ratos, y un botón único obligaría a terminarlo de una sentada o
 * perderlo. Además, un fallo a mitad de un envío masivo dejaría media lista guardada sin decir
 * cuál mitad.
 *
 * **El vacío se distingue del cero.** Una nota sin poner y un 0.0 son estados opuestos —uno es
 * que falta trabajo, el otro es una nota reprobatoria— y con un cero por defecto se verían
 * igual. Por eso el campo empieza vacío y el contador de pendientes va arriba.
 */

import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Alert, Button, Card, CardBody, EmptyState, Skeleton, TextField } from "@/components/ui";
import type { GradeEntry } from "@/features/teaching/api/types";
import { useOfferingRoster, useSetGrade } from "@/features/teaching/hooks";
import { mensajeDeDocencia } from "@/features/teaching/mensajes";

export function RosterPage() {
  const { offeringId } = useParams<{ offeringId: string }>();
  const lista = useOfferingRoster(offeringId ?? null);

  return (
    <div className="space-y-6">
      <div>
        <Link to="/docencia" className="text-brand-700 hover:text-brand-800 text-sm">
          ← Mis grupos
        </Link>
        {lista.data && (
          <>
            <h1 className="text-ink-900 mt-2 text-2xl font-semibold tracking-tight">
              {lista.data.course_name}
            </h1>
            <p className="text-ink-500 mt-1 text-sm">
              <span className="font-mono text-xs">{lista.data.course_code}</span> · grupo{" "}
              {lista.data.group_number} · {lista.data.total}{" "}
              {lista.data.total === 1 ? "inscrito" : "inscritos"}
            </p>
          </>
        )}
      </div>

      {lista.isPending && <ListaCargando />}

      {lista.isError && (
        <Alert tono="error" titulo={mensajeDeDocencia(lista.error).titulo}>
          {mensajeDeDocencia(lista.error).detalle}
        </Alert>
      )}

      {lista.data && lista.data.entries.length === 0 && (
        <EmptyState
          titulo="Nadie se ha inscrito todavía"
          descripcion="Las personas aparecerán aquí a medida que se matriculen en tu grupo."
        />
      )}

      {lista.data && lista.data.entries.length > 0 && (
        <>
          {/* El contador va arriba y no al final: es lo que responde «¿ya terminé?», y esa
              pregunta se hace antes de recorrer la lista, no después. */}
          {lista.data.pending > 0 ? (
            <Alert tono="advertencia" titulo="Quedan notas por poner">
              {lista.data.pending} de {lista.data.total}{" "}
              {lista.data.pending === 1 ? "persona sigue" : "personas siguen"} sin calificar.
              Registro Académico no puede cerrar el período mientras falte alguna.
            </Alert>
          ) : (
            <Alert tono="exito" titulo="Este grupo está completo">
              Todas las notas están puestas. Puedes seguir corrigiéndolas hasta que Registro
              Académico cierre el período.
            </Alert>
          )}

          <ul className="space-y-2">
            {lista.data.entries.map((entrada) => (
              <li key={entrada.student_id}>
                <FilaDeNota offeringId={offeringId ?? ""} entrada={entrada} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function FilaDeNota({ offeringId, entrada }: { offeringId: string; entrada: GradeEntry }) {
  // Arranca con lo que hay guardado, o vacío si no hay nada. Un `0` de partida sería una nota.
  const [nota, setNota] = useState(entrada.final_grade ?? "");
  const guardado = useSetGrade(offeringId);
  const fallo = guardado.isError ? mensajeDeDocencia(guardado.error) : null;

  const cambio = nota.trim() !== (entrada.final_grade ?? "");
  const valida = nota.trim() !== "" && Number(nota) >= 0 && Number(nota) <= 5;

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <p className="text-ink-900 text-sm font-medium">{entrada.full_name}</p>
            <p className="text-ink-500 font-mono text-xs">{entrada.student_code}</p>
          </div>

          <form
            className="flex items-end gap-2"
            onSubmit={(evento) => {
              evento.preventDefault();
              guardado.mutate({ studentId: entrada.student_id, nota: nota.trim() });
            }}
          >
            <TextField
              etiqueta="Nota"
              type="number"
              min={0}
              max={5}
              // `step="any"` y no `step="0.01"`: la validación nativa comprueba el paso con
              // aritmética de coma flotante, y `3.5 / 0.01` no da un entero exacto. El
              // formulario se consideraba inválido y el envío se bloqueaba EN SILENCIO —sin
              // error, sin mensaje— para notas tan normales como 3.5. El rango sigue en
              // `min`/`max`, en el value object y en el CHECK de la base.
              step="any"
              className="w-24"
              value={nota}
              onChange={(e) => {
                setNota(e.target.value);
                // Al volver a escribir, el resultado anterior deja de aplicar. Sin esto, un
                // «Nota guardada» seguiría en pantalla mientras se teclea otra distinta.
                if (guardado.isSuccess || guardado.isError) {
                  guardado.reset();
                }
              }}
              aria-label={`Nota de ${entrada.full_name}`}
            />
            <Button
              type="submit"
              tamano="sm"
              disabled={!cambio || !valida}
              cargando={guardado.isPending}
            >
              Guardar
            </Button>
          </form>
        </div>

        {entrada.final_grade === null && (
          <p className="text-ink-500 text-xs">Sin calificar.</p>
        )}

        {guardado.isSuccess && (
          <p className="text-success-700 text-xs" role="status">
            Nota guardada.
          </p>
        )}

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
      <span className="sr-only">Cargando la lista…</span>
      {Array.from({ length: 5 }, (_, indice) => (
        <li key={indice} className="rounded-card border-ink-200 space-y-2 border bg-white p-5">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3 w-24" />
        </li>
      ))}
    </ul>
  );
}
