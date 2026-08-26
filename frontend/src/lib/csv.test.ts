/**
 * Pruebas de la composición del CSV.
 *
 * Se prueba `componerCsv` y no la descarga: la descarga es tres líneas de DOM sin decisiones, y
 * lo que puede romperse de verdad —y romperse en silencio— es el contenido. Un CSV mal escapado
 * no falla: se abre y muestra datos equivocados, que es mucho peor.
 */

import { describe, expect, it } from "vitest";

import { componerCsv, type ColumnaCsv } from "@/lib/csv";

interface Fila {
  nombre: string;
  valor: number | null;
}

const COLUMNAS: ColumnaCsv<Fila>[] = [
  { encabezado: "Nombre", valor: (f) => f.nombre },
  { encabezado: "Valor", valor: (f) => f.valor },
];

/** Sin el BOM y sin la cabecera, para poder afirmar sobre las filas. */
function filas(csv: string): string[] {
  return csv.replace(/^\uFEFF/, "").split("\r\n").slice(1);
}

describe("composición del CSV", () => {
  it("empieza con BOM y separa por punto y coma", () => {
    // Excel usa el separador de listas del sistema, y en Colombia es el punto y coma. Con
    // comas, todas las columnas se apilan en una sola y parece que la exportación está rota.
    const csv = componerCsv([{ nombre: "Cálculo I", valor: 3 }], COLUMNAS);

    expect(csv.startsWith("\uFEFF")).toBe(true);
    expect(csv).toContain("Nombre;Valor");
    expect(filas(csv)).toEqual(["Cálculo I;3"]);
  });

  it("neutraliza los valores que Excel interpretaría como fórmula", () => {
    // Los nombres los escribe quien administra. Sin el apóstrofo, Excel ejecuta la celda al
    // abrir el archivo, y existen cargas útiles que llegan a lanzar comandos.
    const csv = componerCsv(
      [
        { nombre: "=1+1", valor: 1 },
        { nombre: "+34600", valor: 2 },
        { nombre: "-señas", valor: 3 },
        { nombre: "@dominio", valor: 4 },
      ],
      COLUMNAS,
    );

    expect(filas(csv)).toEqual(["'=1+1;1", "'+34600;2", "'-señas;3", "'@dominio;4"]);
  });

  it("entrecomilla lo que lleva separador, comillas o saltos de línea", () => {
    const csv = componerCsv(
      [
        { nombre: "Álgebra; lineal", valor: 1 },
        { nombre: 'Taller "avanzado"', valor: 2 },
        { nombre: "Dos\nlíneas", valor: 3 },
      ],
      COLUMNAS,
    );

    expect(filas(csv)).toEqual([
      '"Álgebra; lineal";1',
      '"Taller ""avanzado""";2',
      '"Dos\nlíneas";3',
    ]);
  });

  it("deja la celda vacía cuando no hay dato, sin escribir null", () => {
    // «null» en una celda se lee como un valor, y alguien acabaría sumándolo.
    expect(filas(componerCsv([{ nombre: "Sin nota", valor: null }], COLUMNAS))).toEqual([
      "Sin nota;",
    ]);
  });

  it("un reporte sin filas conserva la cabecera", () => {
    // Un archivo completamente vacío no se distingue de una descarga fallida.
    expect(componerCsv<Fila>([], COLUMNAS)).toBe("\uFEFFNombre;Valor");
  });
});
