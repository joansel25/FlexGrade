/**
 * Traducción de los errores de inscripción a algo que el estudiante pueda usar.
 *
 * **Este archivo es el corazón de la iteración.** Los `409` de este flujo NO son averías: son
 * estados normales de una matrícula con miles de personas compitiendo por los mismos cupos.
 * `COURSE_CAPACITY_EXCEEDED` significa «alguien se te adelantó por medio segundo», y la
 * pantalla tiene que decir eso —y qué hacer a continuación— en vez de «Error 409».
 *
 * Cada mensaje trae dos partes deliberadamente:
 *
 * - **`titulo`**: qué pasó, en una frase que se entiende sin contexto técnico.
 * - **`detalle`**: qué se puede hacer al respecto. Sin esto, la persona se queda mirando un
 *   mensaje que la deja igual de bloqueada que antes.
 *
 * Los `details` del error se aprovechan porque `API.md` los define precisamente para esto:
 * `PREREQUISITES_NOT_MET` trae los códigos que faltan y `SCHEDULE_CONFLICT`, el día y la hora
 * del cruce. Interpretarlos evita tener que adivinar leyendo el mensaje del servidor.
 */

import { nombreCompletoDeDia } from "@/features/catalog/horarios";
import { ApiError, NetworkError } from "@/lib/api/errors";

export interface MensajeDeInscripcion {
  titulo: string;
  detalle: string;
  /** `true` cuando conviene refrescar los cupos: el estado del sistema cambió. */
  refrescarCupos: boolean;
}

/** Traduce el fallo de una inscripción. */
export function mensajeDeInscripcion(error: unknown): MensajeDeInscripcion {
  if (error instanceof NetworkError) {
    return {
      titulo: "No se pudo contactar con el servidor",
      // Es importante decir que puede haber entrado: reintentar a ciegas y acabar con dos
      // inscripciones sería peor que revisar.
      detalle:
        "Revisa tu conexión y vuelve a intentarlo. Comprueba antes en «Mis materias» si la " +
        "inscripción alcanzó a registrarse.",
      refrescarCupos: true,
    };
  }

  if (!(error instanceof ApiError)) {
    return {
      titulo: "Ocurrió un problema inesperado",
      detalle: "Vuelve a intentarlo en unos segundos.",
      refrescarCupos: true,
    };
  }

  if (error.is("COURSE_CAPACITY_EXCEEDED")) {
    return {
      titulo: "El grupo se llenó",
      detalle:
        "Alguien tomó el último cupo antes que tú. Los cupos que ves ya están actualizados: " +
        "elige otro grupo de esta materia.",
      refrescarCupos: true,
    };
  }

  if (error.is("ALREADY_ENROLLED")) {
    return {
      titulo: "Ya estás inscrito en este grupo",
      detalle: "Puedes verlo en «Mis materias».",
      refrescarCupos: false,
    };
  }

  if (error.is("SCHEDULE_CONFLICT")) {
    return {
      titulo: "El horario choca con otra materia",
      detalle: describirChoque(error.details),
      refrescarCupos: false,
    };
  }

  if (error.is("PREREQUISITES_NOT_MET")) {
    return {
      titulo: "Te faltan prerrequisitos",
      detalle: describirPrerequisitos(error.details),
      refrescarCupos: false,
    };
  }

  if (error.is("COURSE_NOT_IN_PROGRAM")) {
    return {
      titulo: "Esta materia no es de tu programa",
      detalle:
        "Solo puedes inscribir materias del plan de estudios de tu carrera. Si crees que es " +
        "un error, comunícate con Registro Académico.",
      refrescarCupos: false,
    };
  }

  if (error.is("ENROLLMENT_PERIOD_INACTIVE")) {
    return {
      titulo: "La matrícula no está abierta",
      detalle: "La ventana de inscripción cerró o todavía no ha comenzado.",
      refrescarCupos: false,
    };
  }

  if (error.isAuthError) {
    return {
      titulo: "Tu sesión expiró",
      detalle: "Vuelve a iniciar sesión para continuar con tu matrícula.",
      refrescarCupos: false,
    };
  }

  return {
    titulo: "No se pudo completar la inscripción",
    // Como último recurso, el mensaje del servidor: si el backend añade un código que esta
    // versión no conoce, su explicación es mejor que un texto genérico.
    detalle: error.message,
    refrescarCupos: true,
  };
}

/** Traduce el fallo de una cancelación. */
export function mensajeDeCancelacion(error: unknown): MensajeDeInscripcion {
  if (error instanceof ApiError && error.is("ENROLLMENT_ALREADY_CANCELLED")) {
    return {
      titulo: "Esta inscripción ya estaba cancelada",
      detalle: "Actualiza la página para ver tus materias al día.",
      refrescarCupos: true,
    };
  }

  if (error instanceof ApiError && error.is("ENROLLMENT_NOT_FOUND")) {
    return {
      titulo: "No encontramos esta inscripción",
      detalle: "Puede que ya se haya cancelado. Actualiza la página.",
      refrescarCupos: true,
    };
  }

  const base = mensajeDeInscripcion(error);

  return { ...base, titulo: "No se pudo cancelar la inscripción" };
}

/**
 * Describe con qué choca el horario, usando los `details` del error.
 *
 * `API.md` promete `day_of_week` y `start_time` en el cuerpo. Decir «choca el martes a las
 * 10:00» permite encontrar el conflicto de inmediato; «choca con otra materia», no.
 */
function describirChoque(details: Record<string, unknown>): string {
  const dia = details.day_of_week;
  const hora = details.start_time;

  if (typeof dia === "number" && typeof hora === "string") {
    return (
      `Ya tienes clase el ${nombreCompletoDeDia(dia)} a las ${hora.slice(0, 5)}. ` +
      "Elige otro grupo con un horario distinto o cancela la materia que choca."
    );
  }

  return "Elige otro grupo con un horario distinto o cancela la materia que choca.";
}

/** Enumera los prerrequisitos que faltan, si el error los trae. */
function describirPrerequisitos(details: Record<string, unknown>): string {
  const faltantes = details.missing_prerequisites;

  if (Array.isArray(faltantes) && faltantes.length > 0) {
    const codigos = faltantes.filter((c): c is string => typeof c === "string");

    if (codigos.length > 0) {
      return (
        `Antes debes aprobar: ${codigos.join(", ")}. ` +
        "Consulta la ficha de la materia para ver todos sus prerrequisitos."
      );
    }
  }

  return "Consulta la ficha de la materia para ver qué debes aprobar antes.";
}
