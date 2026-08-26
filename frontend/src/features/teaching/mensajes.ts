/**
 * Traducción de los errores de la actividad docente.
 *
 * Mismo principio que `admin/mensajes.ts` y `enrollment/mensajes.ts`: se decide por `code` y
 * nunca por el texto, porque `API.md` promete estables los códigos y no las redacciones.
 *
 * Los cuatro rechazos de calificar se traducen por separado porque se corrigen en cuatro sitios
 * distintos: revisando la URL, hablando con Registro Académico, aceptando que las notas de un
 * semestre cerrado ya son historia, o entendiendo que esa persona canceló la materia. Un único
 * mensaje mandaría a tres de los cuatro a buscar donde no está el problema.
 */

import { ApiError, NetworkError } from "@/lib/api/errors";

export interface MensajeDeDocencia {
  titulo: string;
  detalle: string;
}

export function mensajeDeDocencia(error: unknown): MensajeDeDocencia {
  if (error instanceof NetworkError) {
    return {
      titulo: "No se pudo contactar con el servidor",
      detalle:
        "Revisa tu conexión y vuelve a intentarlo. Comprueba después si la nota alcanzó a guardarse.",
    };
  }

  if (!(error instanceof ApiError)) {
    return { titulo: "Ocurrió un problema inesperado", detalle: "Vuelve a intentarlo." };
  }

  const traduccion = TRADUCCIONES[error.code];

  if (traduccion !== undefined) {
    return traduccion;
  }

  if (error.status === 422) {
    return {
      titulo: "Esa nota no es válida",
      detalle: "Tiene que estar entre 0.0 y 5.0, con dos decimales como mucho.",
    };
  }

  return { titulo: "No se pudo guardar la nota", detalle: error.message };
}

const TRADUCCIONES: Record<string, MensajeDeDocencia> = {
  OFFERING_NOT_ASSIGNED: {
    titulo: "Ese grupo no es tuyo",
    detalle:
      "Solo puedes calificar los grupos que dictas. Si te asignaron uno nuevo, Registro " +
      "Académico tiene que reflejarlo antes de que aparezca aquí.",
  },
  OFFERING_NOT_FOUND: {
    titulo: "Ese grupo no existe",
    detalle: "Puede que se haya cerrado. Vuelve a tu lista de grupos.",
  },
  GRADING_PERIOD_CLOSED: {
    titulo: "Ese período ya no admite cambios",
    detalle:
      "Las notas de un semestre cerrado ya son historia: cambiarlas movería prerrequisitos " +
      "que otras personas usaron para matricularse. Habla con Registro Académico.",
  },
  STUDENT_NOT_ENROLLED: {
    titulo: "Esa persona no está en este grupo",
    detalle: "Vuelve a cargar la lista: puede que se haya movido de grupo.",
  },
  ENROLLMENT_CANCELLED_CANNOT_GRADE: {
    titulo: "Esa persona canceló la materia",
    detalle:
      "No la cursó, así que no hay nada que calificar. Vuelve a cargar la lista para verla " +
      "como está ahora.",
  },
  PROFESSOR_PROFILE_NOT_FOUND: {
    titulo: "Tu cuenta no está enlazada a tu ficha de docente",
    detalle: "Registro Académico puede enlazarla; hasta entonces no se ven los grupos.",
  },
};
