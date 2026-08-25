/**
 * Mi plan de estudios: la carrera entera, semestre a semestre, con el estado de cada materia.
 *
 * Responde una pregunta que ninguna otra pantalla contesta: «qué me falta para graduarme». El
 * catálogo enseña lo que se ofrece este período y «Mis materias» lo que ya inscribió; solo aquí
 * se ve el recorrido completo y en qué punto está.
 *
 * **Ni un solo estado se decide aquí.** El servidor manda `status` por materia, calculado con
 * los mismos servicios de dominio que aceptan o rechazan una inscripción. Esta pantalla se
 * limita a pintarlo. Si el frontend volviera a razonar «¿tiene los prerrequisitos?», habría dos
 * versiones de la regla y el día que una cambiara la pantalla ofrecería lo que el servidor
 * rechaza, sin forma de que el estudiante entendiera cuál de las dos miente.
 *
 * Solo `AVAILABLE` es pulsable. Atenuar el resto no es decoración: una materia bloqueada que se
 * pudiera pulsar llevaría a una ficha desde la que inscribir algo que va a fallar.
 */

import { Link } from "react-router-dom";

import { Alert, Card, CardBody, EmptyState, Skeleton } from "@/components/ui";
import type { CourseStatus, StudyPlan, StudyPlanEntry } from "@/features/catalog/api/types";
import { useStudyPlan } from "@/features/catalog/hooks";
import { cn } from "@/lib/cn";

/** Cómo se anuncia cada estado y cómo se pinta. */
const ESTADOS: Record<CourseStatus, { etiqueta: string; insignia: string; atenuada: boolean }> = {
  APPROVED: {
    etiqueta: "Aprobada",
    insignia: "bg-success-50 text-success-700 border-success-600/25",
    atenuada: false,
  },
  ENROLLED: {
    etiqueta: "Cursándola",
    insignia: "bg-brand-50 text-brand-800 border-brand-600/20",
    atenuada: false,
  },
  AVAILABLE: {
    etiqueta: "Puedes inscribirla",
    insignia: "bg-white text-ink-700 border-ink-300",
    atenuada: false,
  },
  NOT_OFFERED: {
    etiqueta: "Sin grupos este período",
    insignia: "bg-ink-50 text-ink-600 border-ink-200",
    atenuada: true,
  },
  BLOCKED: {
    etiqueta: "Bloqueada",
    insignia: "bg-warning-50 text-warning-700 border-warning-600/25",
    atenuada: true,
  },
};

export function StudyPlanPage() {
  const { data, isPending, isError, error } = useStudyPlan();

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-ink-900 text-2xl font-semibold tracking-tight sm:text-3xl">
          Mi plan de estudios
        </h1>
        {data && <Resumen plan={data} />}
      </header>

      {isPending && <PlanCargando />}

      {isError && (
        <Alert tono="error" titulo="No se pudo cargar tu plan de estudios">
          {error.message}
        </Alert>
      )}

      {data && data.courses.length === 0 && (
        <EmptyState
          titulo="Tu carrera todavía no tiene plan cargado"
          descripcion="Registro Académico aún no ha publicado las materias de tu programa. Comunícate con ellos si crees que es un error."
        />
      )}

      {data &&
        data.courses.length > 0 &&
        agruparPorSemestre(data.courses).map(([semestre, materias]) => (
          <section key={semestre} aria-labelledby={`semestre-${semestre}`} className="space-y-3">
            <h2
              id={`semestre-${semestre}`}
              className="text-ink-900 border-ink-200 border-b pb-2 text-lg font-semibold"
            >
              Semestre {semestre}
            </h2>
            <ul className="grid gap-3 sm:grid-cols-2">
              {materias.map((materia) => (
                <li key={materia.id}>
                  <FilaDeMateria materia={materia} />
                </li>
              ))}
            </ul>
          </section>
        ))}
    </div>
  );
}

function Resumen({ plan }: { plan: StudyPlan }) {
  // El porcentaje sale de créditos y no de número de materias: un plan mezcla materias de 1 y
  // de 4 créditos, y contarlas por unidades daría un avance que no se corresponde con el
  // esfuerzo real.
  const porcentaje =
    plan.total_credits === 0
      ? 0
      : Math.round((plan.approved_credits / plan.total_credits) * 100);

  return (
    <div className="mt-2 space-y-2">
      <p className="text-ink-600">
        {plan.program_name} · {plan.approved_credits} de {plan.total_credits} créditos aprobados
      </p>
      <div
        className="bg-ink-100 h-2 w-full max-w-md overflow-hidden rounded-full"
        role="progressbar"
        aria-valuenow={porcentaje}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Avance del plan de estudios"
      >
        <div className="bg-success-600 h-full rounded-full" style={{ width: `${porcentaje}%` }} />
      </div>
    </div>
  );
}

function FilaDeMateria({ materia }: { materia: StudyPlanEntry }) {
  const estado = ESTADOS[materia.status];
  const pulsable = materia.status === "AVAILABLE" || materia.status === "ENROLLED";

  const contenido = (
    <CardBody className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="text-brand-700 font-mono text-xs font-semibold">{materia.code}</span>
          <span className="text-ink-900 text-sm font-semibold">{materia.name}</span>
        </div>
        <span
          className={cn("rounded-full border px-2 py-0.5 text-xs font-medium", estado.insignia)}
        >
          {estado.etiqueta}
        </span>
      </div>

      <p className="text-ink-500 text-xs">
        {materia.credits} {materia.credits === 1 ? "crédito" : "créditos"} ·{" "}
        {materia.is_mandatory ? "Obligatoria" : "Electiva"}
      </p>

      {/* El motivo del bloqueo, no solo el bloqueo. «Bloqueada» a secas deja a la persona
          igual de atascada que antes de mirar. */}
      {materia.missing_prerequisites.length > 0 && (
        <p className="text-warning-700 text-xs">
          Antes debes aprobar: {materia.missing_prerequisites.join(", ")}
        </p>
      )}

      {materia.missing_corequisites.length > 0 && (
        <p className="text-warning-700 text-xs">
          Se cursa junto a {materia.missing_corequisites.join(", ")}, que no tiene grupos este
          período.
        </p>
      )}

      {materia.status !== "BLOCKED" && materia.corequisites.length > 0 && (
        <p className="text-ink-600 text-xs">
          Se inscribe junto a {materia.corequisites.join(", ")}
        </p>
      )}
    </CardBody>
  );

  if (!pulsable) {
    // Sin enlace y atenuada: ofrecer entrar a la ficha para no poder hacer nada allí es
    // exactamente el camino que la iteración 6.1 cerró.
    return <Card className={estado.atenuada ? "opacity-60" : undefined}>{contenido}</Card>;
  }

  return (
    <Link
      to={`/catalogo/${materia.id}`}
      className="focus-visible:outline-brand-600 block rounded-card focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
    >
      <Card className="hover:border-brand-300 h-full transition-colors">{contenido}</Card>
    </Link>
  );
}

/**
 * Agrupa las materias por semestre sugerido, en orden.
 *
 * El servidor ya las manda ordenadas por semestre y luego por código, así que aquí solo se
 * parten en tramos: reordenar sería fiarse de dos criterios que pueden divergir.
 */
function agruparPorSemestre(materias: StudyPlanEntry[]): [number, StudyPlanEntry[]][] {
  const porSemestre = new Map<number, StudyPlanEntry[]>();

  for (const materia of materias) {
    const tramo = porSemestre.get(materia.suggested_semester) ?? [];
    tramo.push(materia);
    porSemestre.set(materia.suggested_semester, tramo);
  }

  return [...porSemestre.entries()].sort(([a], [b]) => a - b);
}

function PlanCargando() {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <span className="sr-only">Cargando tu plan de estudios…</span>
      <Skeleton className="h-6 w-32" />
      <ul className="grid gap-3 sm:grid-cols-2">
        {Array.from({ length: 4 }, (_, indice) => (
          <li key={indice} className="rounded-card border-ink-200 space-y-2 border bg-white p-5">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-4 w-24" />
          </li>
        ))}
      </ul>
    </div>
  );
}
