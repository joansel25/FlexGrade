/**
 * Reportes: las cifras del período con gráfica y exportación a CSV.
 *
 * Es la pantalla que le faltaba a los reportes de la Fase 4. Existían los dos endpoints y la
 * única forma de leerlos era Swagger, que devuelve JSON: para llevar una cifra a un comité había
 * que copiarla a mano.
 *
 * **Los números se recalculan en vivo cada 30 s**, igual que el panel de inicio, porque se
 * consultan mientras la matrícula ocurre y una cifra de hace un minuto que parece actual es peor
 * que no tener reporte. Por eso la hora de generación se muestra siempre.
 *
 * **El CSV se arma con los datos que ya están en pantalla**, no pidiendo otra vez al servidor:
 * un segundo viaje devolvería cifras distintas —se calculan en vivo— y el archivo no cuadraría
 * con lo que quien exporta estaba mirando.
 */

import { useState } from "react";

import {
  Alert,
  BarChartConTabla,
  type Barra,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
} from "@/components/ui";
import type { OfferingOccupancy, ProgramEnrollments } from "@/features/admin/api/types";
import { useEnrollmentReport, useOccupancyReport } from "@/features/admin/hooks";
import { mensajeDeAdmin } from "@/features/admin/mensajes";
import { descargarCsv } from "@/lib/csv";

/** A partir de aquí un grupo se considera a punto de llenarse. */
const UMBRAL_DE_ALERTA = 85;

const TAMANOS = [10, 25, 50] as const;

export function ReportsPage() {
  return (
    <div className="space-y-6">
      <InscripcionesPorPrograma />
      <OcupacionDeGrupos />
    </div>
  );
}

function InscripcionesPorPrograma() {
  const reporte = useEnrollmentReport();

  if (reporte.isPending) {
    return <TarjetaCargando titulo="Inscripciones por carrera" />;
  }

  if (reporte.isError) {
    return (
      <Card>
        <CardBody>
          <Alert tono="error" titulo="No se pudo cargar el reporte de inscripciones">
            {mensajeDeAdmin(reporte.error).detalle}
          </Alert>
        </CardBody>
      </Card>
    );
  }

  const { totals: totales, by_program: porPrograma } = reporte.data;
  const barras: Barra[] = porPrograma.map((p) => ({
    etiqueta: `${p.program_code} — ${p.program_name}`,
    valor: p.enrollments,
    anotacion: `${p.enrollments} (${p.students} ${p.students === 1 ? "persona" : "personas"})`,
  }));

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle>Inscripciones por carrera</CardTitle>
          <Generado en={reporte.data.generated_at} periodo={reporte.data.period_code} />
        </div>
        <Button
          variante="secundario"
          tamano="sm"
          disabled={porPrograma.length === 0}
          onClick={() =>
            descargarCsv<ProgramEnrollments>(
              `inscripciones-${reporte.data.period_code}`,
              porPrograma,
              [
                { encabezado: "Código", valor: (p) => p.program_code },
                { encabezado: "Carrera", valor: (p) => p.program_name },
                { encabezado: "Inscripciones", valor: (p) => p.enrollments },
                { encabezado: "Estudiantes", valor: (p) => p.students },
              ],
            )
          }
        >
          Descargar CSV
        </Button>
      </CardHeader>

      <CardBody className="space-y-5">
        <dl className="grid gap-3 sm:grid-cols-3">
          <Cifra etiqueta="Inscripciones" valor={totales.total_enrollments} />
          <Cifra etiqueta="Estudiantes distintos" valor={totales.unique_students} />
          <Cifra etiqueta="Grupos activos" valor={totales.active_offerings} />
        </dl>

        {porPrograma.length === 0 ? (
          <EmptyState
            titulo="Todavía no hay inscripciones"
            descripcion="Las cifras aparecerán en cuanto alguien se matricule en este período."
          />
        ) : (
          <BarChartConTabla barras={barras} encabezado={["Carrera", "Inscripciones"]} />
        )}
      </CardBody>
    </Card>
  );
}

function OcupacionDeGrupos() {
  const [tamano, setTamano] = useState<number>(TAMANOS[0]);
  const reporte = useOccupancyReport(tamano);

  if (reporte.isPending) {
    return <TarjetaCargando titulo="Grupos más llenos" />;
  }

  if (reporte.isError) {
    return (
      <Card>
        <CardBody>
          <Alert tono="error" titulo="No se pudo cargar la ocupación">
            {mensajeDeAdmin(reporte.error).detalle}
          </Alert>
        </CardBody>
      </Card>
    );
  }

  const grupos = reporte.data.offerings;
  const barras: Barra[] = grupos.map((g) => ({
    etiqueta: `${g.course_code} · grupo ${g.group_number}`,
    valor: g.occupancy_rate,
    anotacion: `${Math.round(g.occupancy_rate)}% · ${g.enrolled_count}/${g.total_capacity}`,
    tono: g.occupancy_rate >= UMBRAL_DE_ALERTA ? "alerta" : "normal",
  }));

  return (
    <Card>
      <CardHeader className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle>Grupos más llenos</CardTitle>
          <Generado en={reporte.data.generated_at} periodo={reporte.data.period_code} />
        </div>

        <div className="flex items-end gap-2">
          <label className="block">
            <span className="text-ink-700 mb-1 block text-xs font-medium">Cuántos</span>
            <select
              className="border-ink-300 h-8 rounded-lg border px-2 text-xs"
              value={tamano}
              aria-label="Cuántos grupos mostrar"
              onChange={(e) => setTamano(Number(e.target.value))}
            >
              {TAMANOS.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          <Button
            variante="secundario"
            tamano="sm"
            disabled={grupos.length === 0}
            onClick={() =>
              descargarCsv<OfferingOccupancy>(
                `ocupacion-${reporte.data.period_code}`,
                grupos,
                [
                  { encabezado: "Materia", valor: (g) => g.course_code },
                  { encabezado: "Nombre", valor: (g) => g.course_name },
                  { encabezado: "Grupo", valor: (g) => g.group_number },
                  { encabezado: "Cupo", valor: (g) => g.total_capacity },
                  { encabezado: "Inscritos", valor: (g) => g.enrolled_count },
                  { encabezado: "Disponibles", valor: (g) => g.available_slots },
                  // Redondeado igual que en pantalla: un CSV con 84.6 al lado de un informe
                  // que dice 85 hace dudar de los dos.
                  { encabezado: "Ocupación %", valor: (g) => Math.round(g.occupancy_rate) },
                ],
              )
            }
          >
            Descargar CSV
          </Button>
        </div>
      </CardHeader>

      <CardBody className="space-y-4">
        {grupos.length === 0 ? (
          <EmptyState
            titulo="No hay grupos abiertos en este período"
            descripcion="Abre grupos desde la sección de Grupos para ver su ocupación aquí."
          />
        ) : (
          <>
            <p className="text-ink-500 text-xs">
              Ordenados del más lleno al más vacío. Los grupos al {UMBRAL_DE_ALERTA}% o más van
              marcados: son sobre los que hay que decidir si se amplía el cupo o se abre otro
              grupo, y esa decisión se toma antes de que se llenen, no después.
            </p>
            {/* Tope 100: la ocupación es un porcentaje, así que las barras son comparables
                entre sí y con las de cualquier otra consulta. */}
            <BarChartConTabla barras={barras} maximo={100} encabezado={["Grupo", "Ocupación"]} />
          </>
        )}
      </CardBody>
    </Card>
  );
}

function Cifra({ etiqueta, valor }: { etiqueta: string; valor: number }) {
  return (
    <div className="border-ink-200 rounded-lg border p-3">
      <dt className="text-ink-500 text-xs font-medium">{etiqueta}</dt>
      <dd className="text-ink-900 text-2xl font-semibold tabular-nums">{valor}</dd>
    </div>
  );
}

/** La hora del cálculo. Un reporte sin ella no se sabe si es de ahora o de ayer. */
function Generado({ en, periodo }: { en: string; periodo: string }) {
  const fecha = new Date(en);
  const legible = Number.isNaN(fecha.getTime())
    ? null
    : fecha.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });

  return (
    <p className="text-ink-500 mt-1 text-xs">
      Período {periodo}
      {legible !== null && <> · calculado a las {legible}, se actualiza solo</>}
    </p>
  );
}

function TarjetaCargando({ titulo }: { titulo: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{titulo}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-2" role="status" aria-live="polite">
        <span className="sr-only">Cargando el reporte…</span>
        {Array.from({ length: 4 }, (_, indice) => (
          <Skeleton key={indice} className="h-7 w-full" />
        ))}
      </CardBody>
    </Card>
  );
}
