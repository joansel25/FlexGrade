/**
 * Mi expediente académico: todo lo cursado, semestre a semestre, con su nota.
 *
 * Cierra el círculo visible de la Fase 9. Hasta ahora el semáforo del plan decía «aprobada» sin
 * que el estudiante pudiera ver dónde ni con qué nota, y lo que escribe el cierre del período
 * no tenía dónde leerse. Esta pantalla es ese sitio.
 *
 * **Muestra lo perdido igual que lo aprobado**, y la materia repetida aparece las dos veces,
 * cada una en su semestre. Un expediente que esconde lo reprobado no es un expediente: es
 * justamente el documento donde esa información tiene que estar, y ocultarla haría que no
 * cuadrara con el certificado oficial.
 *
 * **No calcula nada.** Los promedios —el de cada semestre y el acumulado— son ponderados por
 * créditos y llegan hechos del servidor, en `string` con dos decimales. Recalcularlos aquí,
 * aunque fuera con la misma fórmula, crearía una segunda versión de la cifra que decide una
 * beca; y hacerlo en coma flotante desharía la razón por la que el backend usa `Decimal`.
 *
 * Se usa una TABLA y no tarjetas: un expediente se lee comparando filas —qué nota, cuántos
 * créditos—, se copia a un correo y se recorre con lector de pantalla saltando por columnas.
 * Nada de eso funciona con una rejilla de tarjetas.
 */

import { Alert, Card, CardBody, EmptyState, Skeleton } from "@/components/ui";
import type { AcademicHistory, HistoryEntry, HistoryPeriod } from "@/features/transcript/api/types";
import { useAcademicHistory } from "@/features/transcript/hooks";
import { cn } from "@/lib/cn";

/** Cómo se anuncia cada resultado. El color acompaña a la palabra, nunca la sustituye. */
const RESULTADOS: Record<HistoryEntry["status"], { etiqueta: string; insignia: string }> = {
  APPROVED: {
    etiqueta: "Aprobada",
    insignia: "bg-success-50 text-success-700 border-success-600/25",
  },
  FAILED: {
    etiqueta: "Perdida",
    insignia: "bg-danger-50 text-danger-700 border-danger-600/25",
  },
};

export function TranscriptPage() {
  const { data, isPending, isError, error } = useAcademicHistory();

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-ink-900 text-2xl font-semibold tracking-tight sm:text-3xl">
          Mi expediente académico
        </h1>
        {data && <Resumen expediente={data} />}
      </header>

      {isPending && <ExpedienteCargando />}

      {isError && (
        <Alert tono="error" titulo="No se pudo cargar tu expediente">
          {error.message}
        </Alert>
      )}

      {/* Un expediente vacío NO es un error: es el estado normal de quien acaba de ingresar y
          todavía no ha cerrado ningún semestre. Presentarlo como fallo haría que buscara un
          problema donde no lo hay. */}
      {data && data.periods.length === 0 && (
        <EmptyState
          titulo="Todavía no tienes semestres cerrados"
          descripcion="Tu expediente se llena cuando Registro Académico consolida un período. Lo que estés cursando ahora aparecerá aquí al terminar el semestre."
        />
      )}

      {data?.periods.map((periodo) => (
        <SemestreCursado key={periodo.academic_period} periodo={periodo} />
      ))}
    </div>
  );
}

function Resumen({ expediente }: { expediente: AcademicHistory }) {
  return (
    <p className="text-ink-600 mt-2">
      {expediente.full_name} · {expediente.student_code}
      {" · "}
      {/* «en total» no es relleno: cada semestre anuncia también sus créditos aprobados, y sin
          esa palabra las dos cifras se leen como la misma. */}
      {expediente.total_credits_approved}{" "}
      {expediente.total_credits_approved === 1
        ? "crédito aprobado en total"
        : "créditos aprobados en total"}
      {/* El acumulado solo se anuncia cuando hay algo que promediar: un «promedio 0.00» en la
          primera pantalla de quien acaba de ingresar se lee como una nota, no como un vacío. */}
      {expediente.periods.length > 0 && (
        <>
          {" · "}
          promedio acumulado{" "}
          <strong className="text-ink-900 font-semibold tabular-nums">
            {expediente.cumulative_average}
          </strong>
        </>
      )}
    </p>
  );
}

function SemestreCursado({ periodo }: { periodo: HistoryPeriod }) {
  const tituloId = `semestre-${periodo.academic_period}`;

  return (
    <section aria-labelledby={tituloId}>
      <Card>
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id={tituloId} className="text-ink-900 text-lg font-semibold">
              {periodo.academic_period}
            </h2>
            <p className="text-ink-600 text-sm">
              {periodo.credits_approved} de {periodo.credits_attempted} créditos aprobados ·
              promedio{" "}
              <strong className="text-ink-900 font-semibold tabular-nums">
                {periodo.average}
              </strong>
            </p>
          </div>

          {/* La tabla desborda antes que la página: en un móvil, una tabla que ensancha el
              `body` deja toda la interfaz desplazándose en horizontal. */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">
                Materias cursadas en {periodo.academic_period}
              </caption>
              <thead>
                <tr className="text-ink-500 border-ink-200 border-b text-left text-xs">
                  <th scope="col" className="py-1.5 font-medium">
                    Materia
                  </th>
                  <th scope="col" className="py-1.5 text-right font-medium">
                    Créditos
                  </th>
                  <th scope="col" className="py-1.5 text-right font-medium">
                    Nota
                  </th>
                  <th scope="col" className="py-1.5 text-right font-medium">
                    Resultado
                  </th>
                </tr>
              </thead>
              <tbody>
                {/* `course_id` basta como clave DENTRO de un semestre: el
                    `UNIQUE (student_id, course_id, academic_period)` de la base impide que una
                    materia salga dos veces en el mismo. Repetida en otro semestre es otra fila,
                    en otra tabla, y así es como debe verse. */}
                {periodo.entries.map((entrada) => (
                  <FilaCursada key={entrada.course_id} entrada={entrada} />
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </section>
  );
}

function FilaCursada({ entrada }: { entrada: HistoryEntry }) {
  const resultado = RESULTADOS[entrada.status];

  return (
    <tr className="border-ink-100 border-b last:border-0">
      <th scope="row" className="py-2 text-left font-normal">
        <span className="text-brand-700 mr-2 font-mono text-xs font-semibold">{entrada.code}</span>
        <span className="text-ink-900">{entrada.name}</span>
      </th>
      <td className="text-ink-700 py-2 text-right tabular-nums">{entrada.credits}</td>
      <td className="text-ink-900 py-2 text-right font-semibold tabular-nums">
        {entrada.final_grade}
      </td>
      <td className="py-2 text-right">
        <span
          className={cn(
            "inline-block rounded-full border px-2 py-0.5 text-xs font-medium",
            resultado.insignia,
          )}
        >
          {resultado.etiqueta}
        </span>
      </td>
    </tr>
  );
}

function ExpedienteCargando() {
  return (
    <div className="space-y-4" role="status" aria-live="polite">
      <span className="sr-only">Cargando tu expediente académico…</span>
      {Array.from({ length: 2 }, (_, indice) => (
        <div key={indice} className="rounded-card border-ink-200 space-y-3 border bg-white p-5">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
        </div>
      ))}
    </div>
  );
}
