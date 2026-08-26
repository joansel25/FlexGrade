/**
 * Espacios físicos: el inventario y qué hay libre en una franja.
 *
 * La consulta de disponibilidad es lo que la iteración 7.3 construyó en el backend y hasta ahora
 * no tenía interfaz. Sin ella, la única forma de encontrar un aula libre era escribir códigos en
 * el formulario de grupos y coleccionar rechazos: la misma información pedida al revés, un
 * intento cada vez.
 *
 * Las dos mitades usan el MISMO criterio de solapamiento que la restricción de la base, porque
 * las dos preguntan al servidor. Si esta pantalla decidiera por su cuenta qué está libre,
 * ofrecería aulas que el formulario de grupos va a rechazar.
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
import type { AvailableSpace } from "@/features/admin/api/types";
import { useAvailableSpaces, useCreateSpace, useSpaces } from "@/features/admin/hooks";
import { mensajeDeAdmin } from "@/features/admin/mensajes";
import { nombreCompletoDeDia } from "@/features/catalog/horarios";

/** Cómo se nombra cada tipo de espacio en la pantalla. */
const TIPOS: Record<string, string> = {
  CLASSROOM: "Aula",
  LABORATORY: "Laboratorio",
  AUDITORIUM: "Auditorio",
};

export function SpacesPage() {
  return (
    <div className="space-y-6">
      <ConsultaDeDisponibilidad />
      <AltaDeEspacio />
      <Inventario />
    </div>
  );
}

function ConsultaDeDisponibilidad() {
  const [dia, setDia] = useState("1");
  const [desde, setDesde] = useState("08:00");
  const [hasta, setHasta] = useState("10:00");
  const [aforo, setAforo] = useState("");
  const [consulta, setConsulta] = useState<{
    day_of_week: number;
    start_time: string;
    end_time: string;
    min_capacity?: number;
  } | null>(null);

  const disponibles = useAvailableSpaces(consulta);
  const fallo = disponibles.isError ? mensajeDeAdmin(disponibles.error) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Qué aulas están libres</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <form
          className="grid items-end gap-4 sm:grid-cols-[1fr_1fr_1fr_1fr_auto]"
          onSubmit={(evento) => {
            evento.preventDefault();
            setConsulta({
              day_of_week: Number(dia),
              start_time: desde,
              end_time: hasta,
              // Sin aforo mínimo no se envía el filtro: pedir «para 0 personas» no es lo mismo
              // que no pedir nada.
              ...(Number(aforo) > 0 ? { min_capacity: Number(aforo) } : {}),
            });
          }}
        >
          <label className="block">
            <span className="text-ink-700 mb-1 block text-sm font-medium">Día</span>
            <select
              className="border-ink-300 h-10 w-full rounded-lg border px-3 text-sm"
              value={dia}
              onChange={(e) => setDia(e.target.value)}
            >
              {[1, 2, 3, 4, 5, 6].map((d) => (
                <option key={d} value={d}>
                  {nombreCompletoDeDia(d)}
                </option>
              ))}
            </select>
          </label>

          <TextField
            etiqueta="Desde"
            type="time"
            value={desde}
            onChange={(e) => setDesde(e.target.value)}
            required
          />
          <TextField
            etiqueta="Hasta"
            type="time"
            value={hasta}
            onChange={(e) => setHasta(e.target.value)}
            required
          />
          <TextField
            etiqueta="Para cuántos"
            ayuda="Opcional"
            type="number"
            min={1}
            value={aforo}
            onChange={(e) => setAforo(e.target.value)}
          />

          <Button type="submit" cargando={disponibles.isFetching}>
            Consultar
          </Button>
        </form>

        {fallo && (
          <Alert tono="error" titulo={fallo.titulo}>
            {fallo.detalle}
          </Alert>
        )}

        {disponibles.data && (
          <div className="space-y-2">
            <p className="text-ink-600 text-sm">
              {disponibles.data.total}{" "}
              {disponibles.data.total === 1 ? "espacio libre" : "espacios libres"} el{" "}
              {nombreCompletoDeDia(disponibles.data.day_of_week)} de{" "}
              {disponibles.data.start_time.slice(0, 5)} a{" "}
              {disponibles.data.end_time.slice(0, 5)}
            </p>

            {disponibles.data.items.length === 0 ? (
              <EmptyState
                titulo="Ninguno libre en esa franja"
                descripcion="Prueba con otra hora, otro día, o baja el aforo pedido."
              />
            ) : (
              <ul className="flex flex-wrap gap-2">
                {disponibles.data.items.map((espacio) => (
                  <li key={espacio.id}>
                    <Insignia espacio={espacio} />
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function Insignia({ espacio }: { espacio: AvailableSpace }) {
  return (
    <span className="border-ink-200 text-ink-700 inline-flex items-center gap-2 rounded-lg border bg-white px-3 py-1.5 text-sm">
      <span className="text-brand-700 font-mono text-xs font-semibold">{espacio.code}</span>
      <span className="text-ink-500 text-xs">
        {/* Un aforo desconocido se dice, no se disimula con un cero: aparece en la lista
            justamente porque «no sé» no es «no cabe». */}
        {espacio.capacity === null ? "aforo sin registrar" : `${espacio.capacity} personas`}
      </span>
    </span>
  );
}

function AltaDeEspacio() {
  const [code, setCode] = useState("");
  const [tipo, setTipo] = useState("CLASSROOM");
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState("");
  const [building, setBuilding] = useState("");

  const creacion = useCreateSpace();
  const fallo = creacion.isError ? mensajeDeAdmin(creacion.error) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Dar de alta un espacio</CardTitle>
      </CardHeader>
      <CardBody>
        <form
          className="space-y-4"
          onSubmit={(evento) => {
            evento.preventDefault();
            creacion.mutate(
              {
                code: code.trim(),
                space_type: tipo,
                name: name.trim() || null,
                // Sin aforo se manda `null` y no cero: «no lo sé» es un dato legítimo, y un
                // cero sería un aula donde no cabe nadie.
                capacity: Number(capacity) > 0 ? Number(capacity) : null,
                building: building.trim() || null,
              },
              {
                onSuccess: () => {
                  setCode("");
                  setName("");
                  setCapacity("");
                  setBuilding("");
                },
              },
            );
          }}
        >
          <div className="grid gap-4 sm:grid-cols-[1fr_1fr_2fr]">
            <TextField
              etiqueta="Código"
              ayuda="Se guarda en mayúsculas."
              value={code}
              onChange={(e) => setCode(e.target.value)}
              maxLength={20}
              required
            />
            <label className="block">
              <span className="text-ink-700 mb-1 block text-sm font-medium">Tipo</span>
              <select
                className="border-ink-300 h-10 w-full rounded-lg border px-3 text-sm"
                value={tipo}
                onChange={(e) => setTipo(e.target.value)}
              >
                {Object.entries(TIPOS).map(([valor, etiqueta]) => (
                  <option key={valor} value={valor}>
                    {etiqueta}
                  </option>
                ))}
              </select>
            </label>
            <TextField
              etiqueta="Nombre"
              ayuda="Opcional. La mayoría de las aulas solo se numeran."
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={150}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              etiqueta="Aforo"
              ayuda="Opcional. Déjalo vacío si no se ha medido."
              type="number"
              min={1}
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
            />
            <TextField
              etiqueta="Bloque"
              ayuda="Opcional."
              value={building}
              onChange={(e) => setBuilding(e.target.value)}
              maxLength={50}
            />
          </div>

          {fallo && (
            <Alert tono="error" titulo={fallo.titulo}>
              {fallo.detalle}
            </Alert>
          )}

          {creacion.isSuccess && (
            <Alert tono="exito" titulo="Espacio creado">
              Ya se puede asignar a un grupo y aparece en la consulta de disponibilidad.
            </Alert>
          )}

          <Button type="submit" cargando={creacion.isPending} disabled={!code}>
            Dar de alta
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}

function Inventario() {
  const espacios = useSpaces();

  return (
    <section aria-labelledby="inventario" className="space-y-3">
      <h2 id="inventario" className="text-ink-900 text-lg font-semibold">
        Inventario
      </h2>

      {espacios.isPending && <ListaCargando />}

      {espacios.isError && (
        <Alert tono="error" titulo="No se pudo cargar el inventario">
          {mensajeDeAdmin(espacios.error).detalle}
        </Alert>
      )}

      {espacios.data && espacios.data.items.length === 0 && (
        <EmptyState
          titulo="Todavía no hay espacios"
          descripcion="Da de alta el primero con el formulario de arriba."
        />
      )}

      {espacios.data && espacios.data.items.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {espacios.data.items.map((espacio) => (
            <li key={espacio.id}>
              <Card>
                <CardBody>
                  <p className="text-ink-900 text-sm font-medium">
                    <span className="text-brand-700 font-mono text-xs">{espacio.code}</span>{" "}
                    {espacio.name ?? TIPOS[espacio.space_type] ?? espacio.space_type}
                  </p>
                  <p className="text-ink-500 text-xs">
                    {TIPOS[espacio.space_type] ?? espacio.space_type} ·{" "}
                    {espacio.capacity === null
                      ? "aforo sin registrar"
                      : `${espacio.capacity} personas`}
                    {espacio.building && ` · bloque ${espacio.building}`}
                  </p>
                </CardBody>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ListaCargando() {
  return (
    <ul className="grid gap-2 sm:grid-cols-3" role="status" aria-live="polite">
      <span className="sr-only">Cargando el inventario…</span>
      {Array.from({ length: 3 }, (_, indice) => (
        <li key={indice} className="rounded-card border-ink-200 space-y-2 border bg-white p-5">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-24" />
        </li>
      ))}
    </ul>
  );
}
