/**
 * Materias del catálogo: crearlas y verlas.
 *
 * El listado reutiliza `GET /courses`, el mismo endpoint público que ve el estudiante, en vez de
 * pedir uno propio de administración. No hay ninguna diferencia entre las dos preguntas: el
 * catálogo es el catálogo, y un endpoint gemelo solo añadiría un sitio donde las dos listas
 * podrían acabar diciendo cosas distintas.
 *
 * Aquí SÍ se ve el catálogo completo, sin acotar por carrera. Es lo contrario que en la pantalla
 * del estudiante (iteración 6.1), y por la razón opuesta: al estudiante se le acota porque solo
 * puede inscribir lo de su plan, y quien administra necesita ver todo lo que existe para no
 * crear dos veces la misma materia.
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
import { useCreateCourse } from "@/features/admin/hooks";
import { mensajeDeAdmin } from "@/features/admin/mensajes";
import { useCourses } from "@/features/catalog/hooks";

/** Cuántas materias se traen por página en esta pantalla. */
const POR_PAGINA = 50;

export function CoursesPage() {
  const [busqueda, setBusqueda] = useState("");
  const materias = useCourses({ page: 1, size: POR_PAGINA, search: busqueda || undefined });

  return (
    <div className="space-y-6">
      <FormularioDeMateria />

      <section aria-labelledby="catalogo" className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="catalogo" className="text-ink-900 text-lg font-semibold">
            Catálogo completo
          </h2>
          <TextField
            etiqueta="Buscar"
            className="w-full sm:w-72"
            placeholder="Código o nombre"
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
          />
        </div>

        {materias.isPending && <ListaCargando />}

        {materias.isError && (
          <Alert tono="error" titulo="No se pudo cargar el catálogo">
            {mensajeDeAdmin(materias.error).detalle}
          </Alert>
        )}

        {materias.data && materias.data.items.length === 0 && (
          <EmptyState
            titulo="Ninguna materia coincide"
            descripcion="Prueba con otro texto, o crea la materia con el formulario de arriba."
          />
        )}

        {materias.data && materias.data.items.length > 0 && (
          <>
            <ul className="grid gap-2 sm:grid-cols-2">
              {materias.data.items.map((materia) => (
                <li key={materia.id}>
                  <Card>
                    <CardBody>
                      <p className="text-ink-900 text-sm font-medium">
                        <span className="text-brand-700 font-mono text-xs">{materia.code}</span>{" "}
                        {materia.name}
                      </p>
                      <p className="text-ink-500 text-xs">
                        {materia.credits} {materia.credits === 1 ? "crédito" : "créditos"}
                      </p>
                    </CardBody>
                  </Card>
                </li>
              ))}
            </ul>
            {materias.data.total > materias.data.items.length && (
              <p className="text-ink-500 text-xs">
                {/* Se dice cuántas quedan fuera en vez de callarlo: una lista truncada en
                    silencio se lee como la lista completa. */}
                Mostrando {materias.data.items.length} de {materias.data.total}. Usa el buscador
                para encontrar el resto.
              </p>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function FormularioDeMateria() {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [credits, setCredits] = useState("");
  const [description, setDescription] = useState("");

  const creacion = useCreateCourse();
  const fallo = creacion.isError ? mensajeDeAdmin(creacion.error) : null;
  const completo = code && name && Number(credits) > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Crear una materia</CardTitle>
      </CardHeader>
      <CardBody>
        <form
          className="space-y-4"
          onSubmit={(evento) => {
            evento.preventDefault();
            creacion.mutate(
              {
                code: code.trim(),
                name: name.trim(),
                credits: Number(credits),
                description: description.trim() || null,
              },
              {
                onSuccess: () => {
                  setCode("");
                  setName("");
                  setCredits("");
                  setDescription("");
                },
              },
            );
          }}
        >
          <div className="grid gap-4 sm:grid-cols-[1fr_2fr_auto]">
            <TextField
              etiqueta="Código"
              ayuda="Letras y dígitos: MAT101."
              value={code}
              onChange={(e) => setCode(e.target.value)}
              maxLength={20}
              required
            />
            <TextField
              etiqueta="Nombre"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={150}
              required
            />
            <TextField
              etiqueta="Créditos"
              type="number"
              min={1}
              className="sm:w-28"
              value={credits}
              onChange={(e) => setCredits(e.target.value)}
              required
            />
          </div>

          <TextField
            etiqueta="Descripción"
            ayuda="Opcional."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />

          {fallo && (
            <Alert tono="error" titulo={fallo.titulo}>
              {fallo.detalle}
            </Alert>
          )}

          {creacion.isSuccess && (
            <Alert tono="exito" titulo="Materia creada">
              Ya aparece en el catálogo. Para que alguien pueda inscribirla hace falta abrirle un
              grupo y que esté en un plan de estudios.
            </Alert>
          )}

          <Button type="submit" cargando={creacion.isPending} disabled={!completo}>
            Crear materia
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

function ListaCargando() {
  return (
    <ul className="grid gap-2 sm:grid-cols-2" role="status" aria-live="polite">
      <span className="sr-only">Cargando el catálogo…</span>
      {Array.from({ length: 4 }, (_, indice) => (
        <li key={indice} className="rounded-card border-ink-200 space-y-2 border bg-white p-5">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3 w-20" />
        </li>
      ))}
    </ul>
  );
}
