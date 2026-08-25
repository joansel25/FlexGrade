/**
 * Detalle de una materia: sus prerrequisitos y sus grupos con cupos.
 *
 * Es la pantalla desde la que se decide qué grupo inscribir, así que los cupos se refrescan
 * solos cada quince segundos. El botón de inscripción llega en la iteración 5.4; aquí ya está
 * todo lo que hay que ver para elegir.
 */

import { Link, useParams } from "react-router-dom";

import { Alert, Card, CardBody, CardHeader, CardTitle, EmptyState, Skeleton } from "@/components/ui";
import { CapacityBadge } from "@/features/catalog/components/CapacityBadge";
import { ScheduleList } from "@/features/catalog/components/ScheduleList";
import type { Course, Offering } from "@/features/catalog/api/types";
import { useCourseDetail, useCourseOfferings } from "@/features/catalog/hooks";
import { ApiError } from "@/lib/api/errors";

export function CourseDetailPage() {
  const { courseId } = useParams<{ courseId: string }>();

  const materia = useCourseDetail(courseId);
  const grupos = useCourseOfferings(courseId);

  if (materia.isPending) {
    return <DetalleCargando />;
  }

  if (materia.isError) {
    const noExiste = materia.error instanceof ApiError && materia.error.is("COURSE_NOT_FOUND");

    return (
      <div className="space-y-4">
        <EnlaceVolver />
        <Alert tono="error" titulo={noExiste ? "Esta materia no existe" : "No se pudo cargar"}>
          {noExiste
            ? "Puede que el enlace esté mal escrito o que la materia se haya retirado del catálogo."
            : materia.error.message}
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <EnlaceVolver />

      <header>
        <div className="flex items-baseline gap-2">
          <span className="bg-brand-50 text-brand-700 rounded px-2 py-0.5 font-mono text-sm font-semibold">
            {materia.data.code}
          </span>
          <span className="text-ink-500 text-sm">
            {materia.data.credits} {materia.data.credits === 1 ? "crédito" : "créditos"}
          </span>
        </div>

        <h1 className="text-ink-900 mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
          {materia.data.name}
        </h1>

        {materia.data.description && (
          <p className="text-ink-600 mt-2 max-w-2xl">{materia.data.description}</p>
        )}
      </header>

      <Prerequisitos materias={materia.data.prerequisites} />

      <section aria-labelledby="grupos-titulo" className="space-y-3">
        <div className="flex items-center justify-between gap-4">
          <h2 id="grupos-titulo" className="text-ink-900 text-lg font-semibold">
            Grupos disponibles
          </h2>
          {/* Se dice en voz alta que el dato es de ahora mismo: es lo que distingue esta
              pantalla de una captura de hace diez minutos. */}
          <p className="text-ink-500 text-xs">Cupos actualizados en tiempo real</p>
        </div>

        {grupos.isPending && <GruposCargando />}

        {grupos.isError && <ErrorDeGrupos error={grupos.error} />}

        {grupos.data && grupos.data.offerings.length === 0 && (
          <EmptyState
            titulo="Esta materia no tiene grupos abiertos"
            descripcion="No se ofrece en el período de matrícula vigente. Consulta con tu programa si esperabas verla."
          />
        )}

        {grupos.data && grupos.data.offerings.length > 0 && (
          <ul className="space-y-3">
            {grupos.data.offerings.map((grupo) => (
              <li key={grupo.id}>
                <TarjetaDeGrupo grupo={grupo} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function TarjetaDeGrupo({ grupo }: { grupo: Offering }) {
  const lleno = grupo.available_slots <= 0;

  return (
    <Card className={lleno ? "opacity-75" : undefined}>
      <CardBody className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-ink-900 text-base font-semibold">Grupo {grupo.group_number}</span>
            <CapacityBadge disponibles={grupo.available_slots} total={grupo.total_capacity} />
          </div>

          <p className="text-ink-600 text-sm">
            {/* Un grupo puede publicarse sin docente asignado; decirlo evita que el hueco se
                lea como un fallo de carga. */}
            {grupo.professor ?? "Docente por asignar"}
          </p>

          <ScheduleList franjas={grupo.schedule} />
        </div>

        <div className="text-ink-500 shrink-0 text-sm sm:text-right">
          <p>
            {grupo.enrolled_count} / {grupo.total_capacity} inscritos
          </p>
        </div>
      </CardBody>
    </Card>
  );
}

function Prerequisitos({ materias }: { materias: Course[] }) {
  if (materias.length === 0) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Prerrequisitos</CardTitle>
      </CardHeader>
      <CardBody className="space-y-2">
        <p className="text-ink-600 text-sm">
          Debes haber aprobado estas materias antes de inscribir esta.
        </p>
        <ul className="flex flex-wrap gap-2">
          {materias.map((prerequisito) => (
            <li key={prerequisito.id}>
              <Link
                to={`/catalogo/${prerequisito.id}`}
                className="border-ink-200 hover:border-brand-300 hover:bg-brand-50 inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors"
              >
                <span className="text-brand-700 font-mono text-xs font-semibold">
                  {prerequisito.code}
                </span>
                <span className="text-ink-700">{prerequisito.name}</span>
              </Link>
            </li>
          ))}
        </ul>
      </CardBody>
    </Card>
  );
}

function ErrorDeGrupos({ error }: { error: Error }) {
  // «No hay período activo» no es una avería: es el estado normal fuera de la ventana de
  // matrícula, y merece un mensaje que lo explique en vez de uno de error.
  if (error instanceof ApiError && error.is("NO_ACTIVE_PERIOD")) {
    return (
      <Alert tono="info" titulo="No hay matrícula abierta">
        Los grupos se publican cuando se abre la ventana de matrícula del período.
      </Alert>
    );
  }

  return (
    <Alert tono="error" titulo="No se pudieron cargar los grupos">
      {error.message}
    </Alert>
  );
}

function EnlaceVolver() {
  return (
    <Link
      to="/catalogo"
      className="text-brand-700 hover:text-brand-800 inline-flex items-center gap-1 text-sm font-medium"
    >
      <span aria-hidden="true">←</span> Volver al catálogo
    </Link>
  );
}

function DetalleCargando() {
  return (
    <div className="space-y-6" role="status" aria-live="polite">
      <span className="sr-only">Cargando la materia…</span>
      <Skeleton className="h-4 w-32" />
      <div className="space-y-2">
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-4 w-full max-w-2xl" />
      </div>
      <GruposCargando />
    </div>
  );
}

function GruposCargando() {
  return (
    <ul className="space-y-3">
      {Array.from({ length: 2 }, (_, indice) => (
        <li key={indice} className="rounded-card border-ink-200 space-y-3 border bg-white p-5">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-6 w-48" />
        </li>
      ))}
    </ul>
  );
}
