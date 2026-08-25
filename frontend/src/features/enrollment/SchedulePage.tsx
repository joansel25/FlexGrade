/**
 * Horario armado del estudiante.
 *
 * Se pinta como una tabla real (`<table>`), no como una rejilla de `div`. La diferencia importa
 * para quien no ve la pantalla: una tabla permite navegar por celdas y anuncia la cabecera de
 * cada columna, así que al llegar a «Cálculo I» se oye «martes». Con `div` solo se oye una lista
 * de nombres sin saber a qué día pertenecen.
 *
 * En pantallas estrechas la tabla desaparece y se muestra una lista por días: un horario semanal
 * de siete columnas en un móvil es ilegible, y la mayoría de las consultas se hacen desde el
 * teléfono.
 */

import { Alert, Card, CardBody, EmptyState, Skeleton } from "@/components/ui";
import { Link } from "react-router-dom";

import { esSinPeriodoActivo } from "@/features/catalog/hooks";
import { formatearHora, nombreCompletoDeDia, nombreDeDia } from "@/features/catalog/horarios";
import type { StudentScheduleBlock } from "@/features/enrollment/api/types";
import { useMySchedule } from "@/features/enrollment/hooks";

/** Días que se muestran. Sábado y domingo solo aparecen si hay clase. */
const DIAS_LABORALES = [1, 2, 3, 4, 5];

export function SchedulePage() {
  const { data, isPending, isError, error } = useMySchedule();

  const diasConClase = data ? [...new Set(data.blocks.map((b) => b.day_of_week))] : [];
  const dias = [...new Set([...DIAS_LABORALES, ...diasConClase])].sort((a, b) => a - b);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-ink-900 text-2xl font-semibold tracking-tight sm:text-3xl">
          Mi horario
        </h1>
        {data && <p className="text-ink-600 mt-2">Período {data.period}</p>}
      </header>

      {isPending && <Skeleton className="h-64 w-full" />}

      {isError && esSinPeriodoActivo(error) && (
        <Alert tono="info" titulo="No hay matrícula abierta">
          Tu horario aparecerá aquí cuando se abra la ventana de matrícula del período.
        </Alert>
      )}

      {isError && !esSinPeriodoActivo(error) && (
        <Alert tono="error" titulo="No se pudo cargar tu horario">
          {error.message}
        </Alert>
      )}

      {data && data.blocks.length === 0 && (
        <EmptyState
          titulo="Tu horario está vacío"
          descripcion="Cuando inscribas materias, sus clases aparecerán aquí organizadas por día."
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

      {data && data.blocks.length > 0 && (
        <>
          <TablaSemanal dias={dias} bloques={data.blocks} />
          <ListaPorDias dias={dias} bloques={data.blocks} />
        </>
      )}
    </div>
  );
}

function TablaSemanal({ dias, bloques }: { dias: number[]; bloques: StudentScheduleBlock[] }) {
  const filas = Math.max(...dias.map((dia) => bloquesDelDia(bloques, dia).length));

  return (
    <div className="hidden overflow-x-auto lg:block">
      <table className="w-full table-fixed border-collapse text-sm">
        <caption className="sr-only">
          Horario semanal de clases, organizado por día de la semana
        </caption>
        <thead>
          <tr>
            {dias.map((dia) => (
              <th
                key={dia}
                // `scope="col"` es lo que permite al lector de pantalla anunciar el día al
                // entrar en cada celda de esa columna.
                scope="col"
                className="border-ink-200 text-ink-700 border-b px-2 pb-2 text-left text-xs font-semibold uppercase"
              >
                {nombreCompletoDeDia(dia)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: filas }, (_, fila) => (
            <tr key={fila}>
              {dias.map((dia) => {
                const bloque = bloquesDelDia(bloques, dia)[fila];

                return (
                  <td key={dia} className="border-ink-100 border-b p-1 align-top">
                    {bloque ? <Clase bloque={bloque} /> : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ListaPorDias({ dias, bloques }: { dias: number[]; bloques: StudentScheduleBlock[] }) {
  return (
    <div className="space-y-4 lg:hidden">
      {dias.map((dia) => {
        const delDia = bloquesDelDia(bloques, dia);

        if (delDia.length === 0) {
          return null;
        }

        return (
          <section key={dia} aria-labelledby={`dia-${dia}`}>
            <h2
              id={`dia-${dia}`}
              className="text-ink-700 mb-2 text-xs font-semibold uppercase"
            >
              {nombreCompletoDeDia(dia)}
            </h2>
            <ul className="space-y-2">
              {delDia.map((bloque, indice) => (
                <li key={`${bloque.course_code}-${bloque.start_time}-${indice}`}>
                  <Card>
                    <CardBody className="py-3">
                      <Clase bloque={bloque} />
                    </CardBody>
                  </Card>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

function Clase({ bloque }: { bloque: StudentScheduleBlock }) {
  return (
    <div className="bg-brand-50 border-brand-600/20 rounded-lg border px-2.5 py-2">
      <p className="text-brand-800 font-mono text-xs font-semibold">{bloque.course_code}</p>
      <p className="text-ink-800 mt-0.5 text-sm leading-tight font-medium">{bloque.course_name}</p>
      <p className="text-ink-600 mt-1 text-xs">
        {formatearHora(bloque.start_time)}–{formatearHora(bloque.end_time)}
      </p>
      <p className="text-ink-500 text-xs">
        Grupo {bloque.group_number}
        {bloque.classroom && ` · ${bloque.classroom}`}
      </p>
      {/* Lo que el lector de pantalla necesita para situar la clase sin ver la columna. */}
      <span className="sr-only">
        {nombreDeDia(bloque.day_of_week)}, {bloque.professor ?? "docente por asignar"}
      </span>
    </div>
  );
}

/** Clases de un día, ordenadas por hora de inicio. */
function bloquesDelDia(bloques: StudentScheduleBlock[], dia: number): StudentScheduleBlock[] {
  return bloques
    .filter((b) => b.day_of_week === dia)
    .sort((a, b) => a.start_time.localeCompare(b.start_time));
}
