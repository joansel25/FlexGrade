/**
 * Mis grupos: la carga docente del período activo.
 *
 * Es la primera pantalla que el docente tiene en el sistema, y el cimiento de la 9.2: calificar
 * se hace SOBRE un grupo, así que antes hay que poder decir cuáles son suyos.
 *
 * Muestra `enrolled_count` y no cupos libres. Al docente no le sirve saber cuántas plazas
 * quedan —no va a matricular a nadie—; le sirve saber a cuánta gente tiene enfrente, que es un
 * número distinto aunque salga de los mismos datos.
 */

import { Alert, Card, CardBody, EmptyState, Skeleton } from "@/components/ui";
import { ScheduleList } from "@/features/catalog/components/ScheduleList";
import type { ProfessorOffering } from "@/features/teaching/api/types";
import { useMyTeachingLoad } from "@/features/teaching/hooks";

export function TeachingPage() {
  const carga = useMyTeachingLoad();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-ink-900 text-2xl font-semibold tracking-tight">Mis grupos</h1>
        {carga.data?.period_code != null && (
          <p className="text-ink-500 mt-1 text-sm">
            Período {carga.data.period_code} · {carga.data.academic_period}
          </p>
        )}
      </div>

      {carga.isPending && <ListaCargando />}

      {carga.isError && (
        <Alert tono="error" titulo="No se pudo cargar tu carga docente">
          Vuelve a intentarlo en unos segundos. Si sigue fallando, avisa a Registro Académico.
        </Alert>
      )}

      {/* Los dos vacíos se ven igual y significan cosas distintas, así que se dicen distinto:
          sin período no hay semestre abierto; con período, el semestre está abierto y este
          docente no tiene asignación. Un único mensaje mandaría a la mitad a preguntar donde
          no es. */}
      {carga.data && carga.data.items.length === 0 && carga.data.period_code === null && (
        <EmptyState
          titulo="No hay un período de matrícula abierto"
          descripcion="Entre semestres no hay ventana activa. Tus grupos aparecerán aquí cuando Registro Académico abra el siguiente."
        />
      )}

      {carga.data && carga.data.items.length === 0 && carga.data.period_code !== null && (
        <EmptyState
          titulo="No tienes grupos asignados este período"
          descripcion="Si esperabas tener carga, Registro Académico es quien asigna los docentes a los grupos."
        />
      )}

      {carga.data && carga.data.items.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2">
          {carga.data.items.map((grupo) => (
            <li key={grupo.offering_id}>
              <TarjetaDeGrupo grupo={grupo} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TarjetaDeGrupo({ grupo }: { grupo: ProfessorOffering }) {
  return (
    <Card>
      <CardBody className="space-y-3">
        <div>
          <p className="text-ink-900 text-base font-semibold">
            <span className="text-brand-700 font-mono text-xs">{grupo.course_code}</span>{" "}
            {grupo.course_name}
          </p>
          <p className="text-ink-500 text-xs">
            Grupo {grupo.group_number} · {grupo.credits}{" "}
            {grupo.credits === 1 ? "crédito" : "créditos"}
          </p>
        </div>

        <p className="text-ink-700 text-sm">
          <span className="text-ink-900 text-lg font-semibold tabular-nums">
            {grupo.enrolled_count}
          </span>{" "}
          {grupo.enrolled_count === 1 ? "estudiante inscrito" : "estudiantes inscritos"}
          <span className="text-ink-400"> de {grupo.total_capacity} cupos</span>
        </p>

        <ScheduleList franjas={grupo.schedule} />
      </CardBody>
    </Card>
  );
}

function ListaCargando() {
  return (
    <ul className="grid gap-3 sm:grid-cols-2" role="status" aria-live="polite">
      <span className="sr-only">Cargando tus grupos…</span>
      {Array.from({ length: 4 }, (_, indice) => (
        <li key={indice} className="rounded-card border-ink-200 space-y-2 border bg-white p-5">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-3 w-32" />
          <Skeleton className="h-4 w-40" />
        </li>
      ))}
    </ul>
  );
}
