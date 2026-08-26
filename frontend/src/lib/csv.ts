/**
 * Exportación a CSV de lo que hay en pantalla.
 *
 * **Se genera en el cliente, a partir de los datos ya cargados, y no pidiendo un CSV al
 * servidor.** No es por ahorrarse un endpoint: los reportes se calculan en vivo en cada llamada
 * —`API.md` lo fija así porque se consultan mientras la matrícula ocurre—, de modo que un
 * segundo viaje devolvería cifras distintas de las que quien exporta está mirando. Un archivo
 * que no cuadra con la pantalla de la que salió es peor que no tener exportación.
 *
 * Tres decisiones que parecen menores y no lo son:
 *
 * 1. **Separador `;` y no `,`.** Excel usa el separador de listas del sistema, y en la
 *    configuración regional de Colombia —y de casi toda Latinoamérica y España— ese separador
 *    es el punto y coma. Con comas, el archivo se abre con todas las columnas apiladas en una
 *    sola, y quien lo recibe concluye que la exportación está rota.
 * 2. **BOM al principio.** Sin él, Excel lee el archivo como ANSI y «Matemáticas» aparece como
 *    «MatemÃ¡ticas». El BOM es lo que le dice que es UTF-8.
 * 3. **Neutralización de fórmulas.** Los nombres de materias, programas y grupos los escribe
 *    quien administra. Un nombre que empiece por `=`, `+`, `-` o `@` lo interpreta Excel como
 *    una fórmula al abrirlo, y existen cargas útiles que llegan a ejecutar comandos. Se les
 *    antepone un apóstrofo, que Excel no muestra y que corta la interpretación.
 */

/** Una columna del archivo: su encabezado y cómo sacar el valor de cada fila. */
export interface ColumnaCsv<T> {
  encabezado: string;
  valor: (fila: T) => string | number | null | undefined;
}

const SEPARADOR = ";";
const BOM = "\uFEFF";

/** Caracteres con los que Excel empieza a interpretar una celda como fórmula. */
const INICIOS_PELIGROSOS = ["=", "+", "-", "@", "\t", "\r"];

/**
 * Prepara una celda: neutraliza fórmulas y escapa comillas y separadores.
 *
 * El orden importa. Primero se antepone el apóstrofo —si hace falta— y solo después se decide
 * si hay que entrecomillar: al revés, el apóstrofo quedaría dentro de las comillas sin haberse
 * contado para decidir si eran necesarias.
 */
function celda(valor: string | number | null | undefined): string {
  if (valor === null || valor === undefined) {
    return "";
  }

  let texto = String(valor);

  if (INICIOS_PELIGROSOS.some((inicio) => texto.startsWith(inicio))) {
    texto = `'${texto}`;
  }

  if (texto.includes('"') || texto.includes(SEPARADOR) || /[\n\r]/.test(texto)) {
    return `"${texto.replaceAll('"', '""')}"`;
  }

  return texto;
}

/** Compone el contenido del archivo. Se separa de la descarga para poder probarlo sin DOM. */
export function componerCsv<T>(filas: readonly T[], columnas: readonly ColumnaCsv<T>[]): string {
  const lineas = [
    columnas.map((c) => celda(c.encabezado)).join(SEPARADOR),
    ...filas.map((fila) => columnas.map((c) => celda(c.valor(fila))).join(SEPARADOR)),
  ];

  // CRLF: es lo que espera Excel, y lo que pide el RFC 4180.
  return BOM + lineas.join("\r\n");
}

/**
 * Convierte un texto en un nombre de archivo que cualquier sistema acepte.
 *
 * El código del período entra en el nombre y lo escribe quien administra, así que puede traer
 * barras, dos puntos o acentos. Un nombre inválido hace que la descarga falle en silencio en
 * algunos navegadores, que es la peor forma de fallar.
 */
function nombreSeguro(texto: string): string {
  return (
    texto
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/[^a-zA-Z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 100) || "reporte"
  );
}

/**
 * Genera el archivo y lanza la descarga.
 *
 * `revokeObjectURL` en un `setTimeout` y no inmediatamente: Chrome necesita que la URL siga
 * viva durante el tick en que se dispara el clic, y revocarla en la misma línea aborta la
 * descarga sin ningún error visible.
 */
export function descargarCsv<T>(
  nombre: string,
  filas: readonly T[],
  columnas: readonly ColumnaCsv<T>[],
): void {
  const blob = new Blob([componerCsv(filas, columnas)], {
    type: "text/csv;charset=utf-8;",
  });
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");

  enlace.href = url;
  enlace.download = `${nombreSeguro(nombre)}.csv`;
  document.body.append(enlace);
  enlace.click();
  enlace.remove();

  setTimeout(() => URL.revokeObjectURL(url), 0);
}
