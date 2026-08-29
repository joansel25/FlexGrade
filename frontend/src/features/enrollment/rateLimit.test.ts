/**
 * Pruebas de cómo la interfaz traduce el 429 del limitador.
 *
 * Un 429 no es un fallo del sistema ni un error de la persona: es «espera un momento». Traducido
 * como «ocurrió un problema inesperado» produce justo la reacción que hay que evitar —volver a
 * pulsar enseguida—, que agota el límite otra vez y convierte una espera de segundos en una de
 * minutos.
 */

import { describe, expect, it } from "vitest";

import { mensajeDeAdmin } from "@/features/admin/mensajes";
import { mensajeDeInscripcion } from "@/features/enrollment/mensajes";
import { ApiError } from "@/lib/api/errors";

function errorDeLimite(windowSeconds: unknown = 60): ApiError {
  return new ApiError({
    status: 429,
    code: "RATE_LIMIT_EXCEEDED",
    message: "Demasiadas operaciones seguidas.",
    details: { scope: "inscripcion", limit: 30, window_seconds: windowSeconds },
  });
}

describe("el 429 del limitador en la interfaz", () => {
  it("no se presenta como un error inesperado al estudiante", () => {
    const mensaje = mensajeDeInscripcion(errorDeLimite());

    expect(mensaje.titulo).toBe("Vas demasiado rápido");
    expect(mensaje.detalle).toContain("60 segundos");
  });

  it("tranquiliza sobre lo que ya se hizo", () => {
    // Sin esta frase, la duda razonable es «¿se inscribió o no?», y la reacción es reintentar.
    expect(mensajeDeInscripcion(errorDeLimite()).detalle).toContain("no se perdió");
  });

  it("no pide refrescar los cupos", () => {
    // Esa consulta también cuenta contra el límite: pedirla ahora empeoraría justo lo que hay
    // que dejar reposar.
    expect(mensajeDeInscripcion(errorDeLimite()).refrescarCupos).toBe(false);
  });

  it("sobrevive a un error sin la ventana dentro", () => {
    // Si el detalle llegara incompleto, un `undefined segundos` en pantalla se lee como una
    // avería. Se cae al valor por defecto.
    expect(mensajeDeInscripcion(errorDeLimite(null)).detalle).toContain("60 segundos");
  });

  it("le habla distinto a quien administra", () => {
    // Aquí el 429 no es abuso: es alguien de Registro Académico cargando materias en tanda, que
    // es trabajo legítimo.
    const mensaje = mensajeDeAdmin(errorDeLimite());

    expect(mensaje.titulo).toBe("Vas demasiado rápido");
    expect(mensaje.detalle).toContain("no se perdió");
  });
});
