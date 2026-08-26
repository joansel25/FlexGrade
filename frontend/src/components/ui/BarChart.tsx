/**
 * Gráfico de barras horizontales, con `div` y anchos en porcentaje.
 *
 * No se trae una librería de gráficas: este es el único gráfico del producto y una dependencia
 * de ese tamaño pesa más que la pantalla entera que la usaría. Tampoco se dibuja en SVG, que
 * obligaría a superponer las etiquetas en una capa aparte y a mantener las dos alineadas a mano;
 * con `div` la etiqueta vive DENTRO de la barra y no puede desalinearse.
 *
 * **La tabla es la fuente de la verdad, no las barras.** Las barras van `aria-hidden`: un lector
 * de pantalla no puede leer una proporción, y anunciarla sería una versión resumida de un dato
 * que ya está completo y navegable justo debajo. La tabla también es lo que se puede copiar a un
 * informe.
 */

export interface Barra {
  etiqueta: string;
  valor: number;
  /** Lo que se muestra como cifra. Por defecto, el valor. Sirve para «84%» o «38 / 45». */
  anotacion?: string;
  /** `alerta` marca lo que está a punto de llenarse. */
  tono?: "normal" | "alerta";
}

const TONOS = {
  normal: "bg-brand-500",
  alerta: "bg-warning-600",
} as const;

export function BarChartConTabla({
  barras,
  maximo,
  encabezado,
}: {
  barras: Barra[];
  maximo?: number;
  encabezado: [string, string];
}) {
  if (barras.length === 0) {
    return null;
  }

  // El máximo se puede fijar desde fuera —la ocupación siempre se mide sobre 100— para que dos
  // gráficos sean comparables. Nunca cero: dividir por cero daría un ancho `NaN` que el
  // navegador descarta en silencio, y todas las barras saldrían vacías sin ningún error.
  const tope = Math.max(maximo ?? Math.max(...barras.map((b) => b.valor)), 1);

  return (
    <div className="space-y-4">
      <ul className="space-y-1.5" aria-hidden="true">
        {barras.map((barra) => (
          <li key={barra.etiqueta} className="bg-ink-100 relative h-7 overflow-hidden rounded">
            <div
              className={`h-full rounded ${TONOS[barra.tono ?? "normal"]}`}
              style={{ width: `${Math.min((barra.valor / tope) * 100, 100)}%` }}
            />
            <div className="absolute inset-0 flex items-center justify-between gap-2 px-2 text-xs">
              <span className="text-ink-900 truncate font-medium">{barra.etiqueta}</span>
              <span className="text-ink-800 shrink-0 font-semibold tabular-nums">
                {barra.anotacion ?? barra.valor}
              </span>
            </div>
          </li>
        ))}
      </ul>

      <table className="w-full text-sm">
        <thead>
          <tr className="text-ink-500 border-ink-200 border-b text-left text-xs">
            <th scope="col" className="py-1 font-medium">
              {encabezado[0]}
            </th>
            <th scope="col" className="py-1 text-right font-medium">
              {encabezado[1]}
            </th>
          </tr>
        </thead>
        <tbody>
          {barras.map((barra) => (
            <tr key={barra.etiqueta} className="border-ink-100 border-b last:border-0">
              <th scope="row" className="text-ink-900 py-1.5 text-left font-normal">
                {barra.etiqueta}
              </th>
              <td className="text-ink-700 py-1.5 text-right tabular-nums">
                {barra.anotacion ?? barra.valor}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
