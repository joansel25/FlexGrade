/**
 * Pruebas de cómo la interfaz traduce «ya cursas esta materia en otro grupo».
 *
 * El 409 es nuevo: hasta la corrección del hallazgo #1 el sistema dejaba inscribirse en dos
 * grupos de la misma materia, y `academic_history` —único por materia— hacía imposible cerrar
 * el semestre después.
 *
 * Lo que se comprueba aquí es que el mensaje sea ACCIONABLE. La persona no ha hecho nada raro:
 * pulsó «Inscribir» en un grupo que la pantalla le ofrecía. Si el mensaje no dice en qué grupo
 * está ya ni cómo cambiarse, se queda mirando un rechazo que parece un fallo del sistema.
 */

import { describe, expect, it } from "vitest";

import { mensajeDeInscripcion } from "@/features/enrollment/mensajes";
import { ApiError } from "@/lib/api/errors";

function errorDeMateriaRepetida(grupo: unknown = "01"): ApiError {
  return new ApiError({
    status: 409,
    code: "ALREADY_ENROLLED_IN_COURSE",
    message: "Ya estás cursando esta materia en otro grupo",
    details: {
      course_id: "3c81b90d-5756-4769-868f-5cbd527473f3",
      enrolled_offering_id: "6d8cbc18-21cb-46f0-b3ef-a17769ab179c",
      enrolled_group_number: grupo,
    },
  });
}

describe("la materia ya inscrita en otro grupo", () => {
  it("no se presenta como un error inesperado", () => {
    expect(mensajeDeInscripcion(errorDeMateriaRepetida()).titulo).toBe(
      "Ya estás cursando esta materia",
    );
  });

  it("nombra el grupo que ya tiene", () => {
    // «Ya la cursas» a secas deja a la persona buscando dónde, y creyendo que el sistema se
    // equivocó: la pantalla acababa de ofrecerle el botón.
    expect(mensajeDeInscripcion(errorDeMateriaRepetida("03")).detalle).toContain("grupo 03");
  });

  it("dice cómo cambiarse, que es lo único que puede hacer", () => {
    expect(mensajeDeInscripcion(errorDeMateriaRepetida()).detalle).toContain("cancela primero");
  });

  it("no pide refrescar los cupos", () => {
    // El rechazo no tiene nada que ver con la disponibilidad: los cupos que ve son correctos.
    expect(mensajeDeInscripcion(errorDeMateriaRepetida()).refrescarCupos).toBe(false);
  });

  it("sobrevive a un error sin el número de grupo dentro", () => {
    // Un «grupo undefined» en pantalla se lee como una avería. Se cae a un texto que sigue
    // diciendo qué hacer, aunque sin poder nombrar el grupo.
    const detalle = mensajeDeInscripcion(errorDeMateriaRepetida(null)).detalle;

    expect(detalle).not.toContain("undefined");
    expect(detalle).toContain("Cancela el que tienes");
  });
});
