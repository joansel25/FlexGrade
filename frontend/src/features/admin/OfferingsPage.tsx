/**
 * Grupos: abrirlos y ajustar su cupo.
 *
 * Es el formulario más rico de administración porque es donde se cruzan las tres reglas que las
 * fases anteriores construyeron: la materia tiene que existir, el horario no puede cruzarse
 * consigo mismo, y el aula tiene que estar libre y tener sitio. Ninguna se comprueba aquí —el
 * servidor las decide y esta pantalla traduce lo que responde—, porque duplicarlas en el
 * navegador garantiza que un día discrepen.
 *
 * EL DOCENTE NO SE PIDE, aunque la API lo acepte. No existe endpoint para listar profesores, así
 * que el campo solo podría ser un UUID escrito a mano: pedirlo así causaría más errores de los
 * que evita. `professor_id` es opcional en la API y se asigna después; cuando exista el listado,
 * el campo llega con un selector de verdad.
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
  TextField,
} from "@/components/ui";
import type { NewScheduleBlock } from "@/features/admin/api/types";
import { useAdjustCapacity, useCreateOffering, useOccupancyReport } from "@/features/admin/hooks";
import { mensajeDeAdmin } from "@/features/admin/mensajes";
import { nombreCompletoDeDia } from "@/features/catalog/horarios";
import { useCourses } from "@/features/catalog/hooks";

/** Una franja en blanco, como la que se añade al pulsar «Añadir franja». */
const FRANJA_VACIA: NewScheduleBlock = {
  day_of_week: 1,
  start_time: "08:00",
  end_time: "10:00",
  space_code: "",
};

export function OfferingsPage() {
  return (
    <div className="space-y-6">
      <FormularioDeGrupo />
      <AjusteDeCupos />
    </div>
  );
}

function FormularioDeGrupo() {
  const [courseId, setCourseId] = useState("");
  const [groupNumber, setGroupNumber] = useState("");
  const [capacity, setCapacity] = useState("");
  const [franjas, setFranjas] = useState<NewScheduleBlock[]>([{ ...FRANJA_VACIA }]);

  const materias = useCourses({ page: 1, size: 100 });
  const creacion = useCreateOffering();
  const fallo = creacion.isError ? mensajeDeAdmin(creacion.error) : null;
  const completo = courseId && groupNumber && Number(capacity) > 0;

  const cambiarFranja = (indice: number, cambio: Partial<NewScheduleBlock>) => {
    setFranjas((actuales) =>
      actuales.map((franja, i) => (i === indice ? { ...franja, ...cambio } : franja)),
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Abrir un grupo</CardTitle>
      </CardHeader>
      <CardBody>
        <form
          className="space-y-4"
          onSubmit={(evento) => {
            evento.preventDefault();
            creacion.mutate(
              {
                course_id: courseId,
                group_number: groupNumber.trim(),
                total_capacity: Number(capacity),
                schedule: franjas.map((franja) => ({
                  ...franja,
                  // Un aula en blanco es «sin asignar», que es un estado legítimo: el horario
                  // se publica antes de repartir espacios. La cadena vacía no lo es.
                  space_code: franja.space_code?.trim() || null,
                })),
              },
              {
                onSuccess: () => {
                  setGroupNumber("");
                  setCapacity("");
                  setFranjas([{ ...FRANJA_VACIA }]);
                },
              },
            );
          }}
        >
          <div className="grid gap-4 sm:grid-cols-[2fr_1fr_1fr]">
            <label className="block">
              <span className="text-ink-700 mb-1 block text-sm font-medium">Materia</span>
              <select
                className="border-ink-300 focus:border-brand-500 focus:ring-brand-500/20 h-10 w-full rounded-lg border px-3 text-sm focus:ring-4 focus:outline-none"
                value={courseId}
                onChange={(e) => setCourseId(e.target.value)}
                required
              >
                <option value="">Elige una materia…</option>
                {materias.data?.items.map((materia) => (
                  <option key={materia.id} value={materia.id}>
                    {materia.code} — {materia.name}
                  </option>
                ))}
              </select>
            </label>

            <TextField
              etiqueta="Grupo"
              ayuda="01, 02…"
              value={groupNumber}
              onChange={(e) => setGroupNumber(e.target.value)}
              maxLength={10}
              required
            />
            <TextField
              etiqueta="Cupos"
              type="number"
              min={1}
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
              required
            />
          </div>

          <fieldset className="space-y-3">
            <legend className="text-ink-700 text-sm font-medium">Horario</legend>

            {franjas.map((franja, indice) => (
              <div
                key={indice}
                className="border-ink-200 grid items-end gap-3 rounded-lg border p-3 sm:grid-cols-[1fr_1fr_1fr_1fr_auto]"
              >
                <label className="block">
                  <span className="text-ink-700 mb-1 block text-sm font-medium">Día</span>
                  <select
                    className="border-ink-300 h-10 w-full rounded-lg border px-3 text-sm"
                    value={franja.day_of_week}
                    onChange={(e) =>
                      cambiarFranja(indice, { day_of_week: Number(e.target.value) })
                    }
                  >
                    {[1, 2, 3, 4, 5, 6].map((dia) => (
                      <option key={dia} value={dia}>
                        {nombreCompletoDeDia(dia)}
                      </option>
                    ))}
                  </select>
                </label>

                <TextField
                  etiqueta="Desde"
                  type="time"
                  value={franja.start_time}
                  onChange={(e) => cambiarFranja(indice, { start_time: e.target.value })}
                  required
                />
                <TextField
                  etiqueta="Hasta"
                  type="time"
                  value={franja.end_time}
                  onChange={(e) => cambiarFranja(indice, { end_time: e.target.value })}
                  required
                />
                <TextField
                  etiqueta="Aula"
                  ayuda="Opcional"
                  placeholder="A-201"
                  value={franja.space_code ?? ""}
                  onChange={(e) => cambiarFranja(indice, { space_code: e.target.value })}
                />

                <Button
                  variante="secundario"
                  tamano="sm"
                  type="button"
                  disabled={franjas.length === 1}
                  onClick={() => setFranjas((a) => a.filter((_, i) => i !== indice))}
                  aria-label={`Quitar la franja ${indice + 1}`}
                >
                  Quitar
                </Button>
              </div>
            ))}

            <Button
              variante="secundario"
              tamano="sm"
              type="button"
              onClick={() => setFranjas((a) => [...a, { ...FRANJA_VACIA }])}
            >
              Añadir franja
            </Button>
          </fieldset>

          {fallo && (
            <Alert tono="error" titulo={fallo.titulo}>
              {fallo.detalle}
            </Alert>
          )}

          {creacion.isSuccess && (
            <Alert tono="exito" titulo="Grupo abierto">
              Ya aparece en el catálogo del período activo.
            </Alert>
          )}

          <Button type="submit" cargando={creacion.isPending} disabled={!completo}>
            Abrir grupo
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

/**
 * Ajuste de cupos sobre los grupos más llenos.
 *
 * Se listan los más llenos y no todos porque son los únicos sobre los que hay una decisión
 * pendiente: ampliar el cupo o abrir otro grupo. Un listado completo de cientos de grupos para
 * tocar cinco sería ruido.
 */
function AjusteDeCupos() {
  const ocupacion = useOccupancyReport(10);

  return (
    <section aria-labelledby="cupos" className="space-y-3">
      <h2 id="cupos" className="text-ink-900 text-lg font-semibold">
        Ajustar cupos
      </h2>
      <p className="text-ink-600 text-sm">
        Los grupos más llenos del período, que son sobre los que hay algo que decidir.
      </p>

      {ocupacion.isError && (
        <Alert tono="error" titulo="No se pudo cargar la ocupación">
          {mensajeDeAdmin(ocupacion.error).detalle}
        </Alert>
      )}

      {ocupacion.data && ocupacion.data.offerings.length === 0 && (
        <EmptyState
          titulo="Todavía no hay grupos con inscritos"
          descripcion="Aparecerán aquí en cuanto empiecen las inscripciones."
        />
      )}

      {ocupacion.data && ocupacion.data.offerings.length > 0 && (
        <ul className="space-y-2">
          {ocupacion.data.offerings.map((grupo) => (
            <li key={grupo.offering_id}>
              <FilaDeCupo
                offeringId={grupo.offering_id}
                etiqueta={`${grupo.course_code} grupo ${grupo.group_number}`}
                inscritos={grupo.enrolled_count}
                capacidad={grupo.total_capacity}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function FilaDeCupo({
  offeringId,
  etiqueta,
  inscritos,
  capacidad,
}: {
  offeringId: string;
  etiqueta: string;
  inscritos: number;
  capacidad: number;
}) {
  const [nuevo, setNuevo] = useState(String(capacidad));
  const ajuste = useAdjustCapacity();

  const fallo = ajuste.isError ? mensajeDeAdmin(ajuste.error) : null;
  const cambio = Number(nuevo) !== capacidad && Number(nuevo) > 0;

  return (
    <Card>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-ink-900 text-sm font-medium">{etiqueta}</p>
            <p className="text-ink-500 text-xs">
              {inscritos} inscritos de {capacidad} cupos
            </p>
          </div>

          <div className="flex items-end gap-2">
            <TextField
              etiqueta="Cupo total"
              type="number"
              min={inscritos || 1}
              className="w-28"
              value={nuevo}
              onChange={(e) => setNuevo(e.target.value)}
              aria-label={`Cupo total de ${etiqueta}`}
            />
            <Button
              tamano="sm"
              disabled={!cambio}
              cargando={ajuste.isPending}
              onClick={() =>
                ajuste.mutate({ offeringId, totalCapacity: Number(nuevo) })
              }
            >
              Guardar
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
