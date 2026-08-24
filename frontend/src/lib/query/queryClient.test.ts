/**
 * Pruebas de la política de reintentos.
 *
 * Es una decisión con consecuencias directas en el pico de matrícula: reintentar un 409
 * significa insistirle al servidor sobre un cupo que ya no existe, multiplicando peticiones
 * justo cuando está más cargado, y retrasar el mensaje que el estudiante necesita leer.
 */

import { describe, expect, it } from "vitest";

import { ApiError, NetworkError } from "@/lib/api/errors";
import { crearQueryClient } from "@/lib/query/queryClient";

function politicaDeReintento() {
  const opciones = crearQueryClient().getDefaultOptions().queries;
  const retry = opciones?.retry;

  if (typeof retry !== "function") {
    throw new Error("La política de reintentos debe ser una función");
  }

  return retry;
}

describe("política de reintentos de las consultas", () => {
  it("no reintenta los errores 4xx", () => {
    const conflicto = new ApiError({
      status: 409,
      code: "COURSE_CAPACITY_EXCEEDED",
      message: "Sin cupos",
    });

    expect(politicaDeReintento()(0, conflicto)).toBe(false);
  });

  it("reintenta los 5xx, que suelen ser una instancia que se está reemplazando", () => {
    const fallo = new ApiError({ status: 503, code: "DOMAIN_ERROR", message: "No disponible" });

    expect(politicaDeReintento()(0, fallo)).toBe(true);
  });

  it("reintenta los fallos de red", () => {
    expect(politicaDeReintento()(0, new NetworkError("sin conexión"))).toBe(true);
  });

  it("deja de reintentar tras dos intentos", () => {
    const fallo = new NetworkError("sin conexión");

    expect(politicaDeReintento()(2, fallo)).toBe(false);
  });

  it("nunca reintenta una mutación", () => {
    // Inscribir dos veces por un reintento automático es justo lo que el sistema entero
    // existe para evitar.
    expect(crearQueryClient().getDefaultOptions().mutations?.retry).toBe(false);
  });
});
