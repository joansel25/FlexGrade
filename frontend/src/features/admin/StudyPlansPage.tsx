/**
 * Planes de estudio: qué materias tiene cada carrera, en qué semestre y si son obligatorias.
 *
 * QUITAR UNA MATERIA PUEDE SER DESTRUCTIVO SIN PARECERLO, y esta pantalla lo trata como tal. La
 * clave foránea de los requisitos apunta al plan con `ON DELETE CASCADE`, así que sacar
 * `MAT101` borraría en silencio el requisito «`MAT102` exige `MAT101`». El servidor lo rechaza
 * nombrando quién depende (iteración 8.3), y aquí se muestra ese motivo en vez de un «no se
 * pudo».
 *
 * Los requisitos —añadir y quitar prerrequisitos y correquisitos— NO se editan todavía: falta
 * decidir si son retroactivos, y esa decisión cambia el modelo de datos si la respuesta es que
 * no. Construir la pantalla antes obligaría a rehacerla.
 */

import { useState } from "react";

import {
  Alert,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
  TextField,
} from "@/components/ui";
import { useProgramPlan, usePrograms, useRemovePlanCourse, useSetPlanCourse } from "@/features/admin/hooks";
import { mensajeDeAdmin } from "@/features/admin/mensajes";
import type { StudyPlanEntry } from "@/features/catalog/api/types";
import { useCourses } from "@/features/catalog/hooks";

export function StudyPlansPage() {
  const programas = usePrograms();
  const [programId, setProgramId] = useState<string | null>(null);

  // Se elige el primero en cuanto llegan: una pantalla que empieza vacía obliga a un clic para
  // ver lo que casi siempre se quiere ver.
  const elegido = programId ?? programas.data?.items[0]?.id ?? null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Elegir la carrera</CardTitle>
        </CardHeader>
        <CardBody>
          {programas.isError && (
            <Alert tono="error" titulo="No se pudieron cargar los programas">
              {mensajeDeAdmin(programas.error).detalle}
            </Alert>
          )}

          <label className="block max-w-md">
            <span className="text-ink-700 mb-1 block text-sm font-medium">Carrera</span>
            <select
              className="border-ink-300 h-10 w-full rounded-lg border px-3 text-sm"
              value={elegido ?? ""}
              onChange={(e) => setProgramId(e.target.value)}
            >
              {programas.data?.items.map((programa) => (
                <option key={programa.id} value={programa.id}>
                  {programa.code} — {programa.name}
                </option>
              ))}
            </select>
          </label>
        </CardBody>
      </Card>

      {elegido !== null && <EditorDePlan programId={elegido} />}
    </div>
  );
}

function EditorDePlan({ programId }: { programId: string }) {
  const plan = useProgramPlan(programId);

  return (
    <div className="space-y-6">
      <AnadirMateria programId={programId} yaEnElPlan={plan.data?.courses ?? []} />

      <section aria-labelledby="materias-del-plan" className="space-y-3">
        <h2 id="materias-del-plan" className="text-ink-900 text-lg font-semibold">
          Materias del plan
        </h2>

        {plan.isPending && <ListaCargando />}

        {plan.isError && (
          <Alert tono="error" titulo="No se pudo cargar el plan">
            {mensajeDeAdmin(plan.error).detalle}
          </Alert>
        )}

        {plan.data && plan.data.courses.length === 0 && (
          <EmptyState
            titulo="Esta carrera todavía no tiene plan"
            descripcion="Añade la primera materia con el formulario de arriba."
          />
        )}

        {plan.data && plan.data.courses.length > 0 && (
          <>
            <p className="text-ink-500 text-xs">
              {plan.data.courses.length} materias · {plan.data.total_credits} créditos ·{" "}
              {plan.data.total_semesters} semestres
            </p>
            <ul className="space-y-2">
              {plan.data.courses.map((materia) => (
                <li key={materia.id}>
                  <FilaDelPlan programId={programId} materia={materia} />
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
    </div>
  );
}

function AnadirMateria({
  programId,
  yaEnElPlan,
}: {
  programId: string;
  yaEnElPlan: StudyPlanEntry[];
}) {
  const [courseId, setCourseId] = useState("");
  const [semestre, setSemestre] = useState("1");
  const [obligatoria, setObligatoria] = useState(true);

  const materias = useCourses({ page: 1, size: 100 });
  const guardado = useSetPlanCourse(programId);
  const fallo = guardado.isError ? mensajeDeAdmin(guardado.error) : null;

  // Las que ya están no se ofrecen: añadirlas nunca es lo que se quiere, y para cambiarles el
  // semestre está la fila de abajo.
  const enElPlan = new Set(yaEnElPlan.map((m) => m.id));
  const disponibles = materias.data?.items.filter((m) => !enElPlan.has(m.id)) ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Añadir una materia al plan</CardTitle>
      </CardHeader>
      <CardBody>
        <form
          className="space-y-4"
          onSubmit={(evento) => {
            evento.preventDefault();
            guardado.mutate(
              {
                courseId,
                suggested_semester: Number(semestre),
                is_mandatory: obligatoria,
              },
              { onSuccess: () => setCourseId("") },
            );
          }}
        >
          <div className="grid items-end gap-4 sm:grid-cols-[2fr_1fr_auto]">
            <label className="block">
              <span className="text-ink-700 mb-1 block text-sm font-medium">Materia</span>
              <select
                className="border-ink-300 h-10 w-full rounded-lg border px-3 text-sm"
                value={courseId}
                onChange={(e) => setCourseId(e.target.value)}
                required
              >
                <option value="">Elige una materia…</option>
                {disponibles.map((materia) => (
                  <option key={materia.id} value={materia.id}>
                    {materia.code} — {materia.name}
                  </option>
                ))}
              </select>
            </label>

            <TextField
              etiqueta="Semestre"
              type="number"
              min={1}
              value={semestre}
              onChange={(e) => setSemestre(e.target.value)}
              required
            />

            <label className="flex h-10 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="border-ink-300 h-4 w-4 rounded"
                checked={obligatoria}
                onChange={(e) => setObligatoria(e.target.checked)}
              />
              Obligatoria
            </label>
          </div>

          {fallo && (
            <Alert tono="error" titulo={fallo.titulo}>
              {fallo.detalle}
            </Alert>
          )}

          <Button type="submit" cargando={guardado.isPending} disabled={!courseId}>
            Añadir al plan
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

function FilaDelPlan({ programId, materia }: { programId: string; materia: StudyPlanEntry }) {
  const [semestre, setSemestre] = useState(String(materia.suggested_semester));
  const [obligatoria, setObligatoria] = useState(materia.is_mandatory);

  const guardado = useSetPlanCourse(programId);
  const retirada = useRemovePlanCourse(programId);

  const fallo = guardado.isError
    ? mensajeDeAdmin(guardado.error)
    : retirada.isError
      ? mensajeDeAdmin(retirada.error)
      : null;

  const cambio =
    Number(semestre) !== materia.suggested_semester || obligatoria !== materia.is_mandatory;

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <p className="text-ink-900 text-sm font-medium">
              <span className="text-brand-700 font-mono text-xs">{materia.code}</span>{" "}
              {materia.name}
            </p>
            <p className="text-ink-500 text-xs">
              {materia.credits} {materia.credits === 1 ? "crédito" : "créditos"}
              {materia.corequisites.length > 0 && (
                <> · se cursa junto a {materia.corequisites.join(", ")}</>
              )}
            </p>
          </div>

          <div className="flex flex-wrap items-end gap-2">
            <TextField
              etiqueta="Semestre"
              type="number"
              min={1}
              className="w-24"
              value={semestre}
              onChange={(e) => setSemestre(e.target.value)}
              aria-label={`Semestre de ${materia.code}`}
            />
            <label className="flex h-10 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="border-ink-300 h-4 w-4 rounded"
                checked={obligatoria}
                onChange={(e) => setObligatoria(e.target.checked)}
                aria-label={`${materia.code} es obligatoria`}
              />
              Obligatoria
            </label>
            <Button
              tamano="sm"
              disabled={!cambio}
              cargando={guardado.isPending}
              onClick={() =>
                guardado.mutate({
                  courseId: materia.id,
                  suggested_semester: Number(semestre),
                  is_mandatory: obligatoria,
                })
              }
            >
              Guardar
            </Button>
            <Button
              variante="peligro"
              tamano="sm"
              cargando={retirada.isPending}
              onClick={() => retirada.mutate(materia.id)}
              aria-label={`Quitar ${materia.code} del plan`}
            >
              Quitar
            </Button>
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
    <ul className="space-y-2" role="status" aria-live="polite">
      <span className="sr-only">Cargando el plan…</span>
      {Array.from({ length: 3 }, (_, indice) => (
        <li key={indice} className="rounded-card border-ink-200 space-y-2 border bg-white p-5">
          <Skeleton className="h-4 w-64" />
          <Skeleton className="h-3 w-32" />
        </li>
      ))}
    </ul>
  );
}
