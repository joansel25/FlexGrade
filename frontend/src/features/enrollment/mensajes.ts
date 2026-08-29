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

  if (error.is("COREQUISITES_NOT_MET")) {
    return {
      titulo: "Falta inscribir una materia que va junto a esta",
      // A diferencia del prerrequisito, esto SÍ se puede resolver ahora mismo: el detalle
      // tiene que decirlo, o la persona lee «te falta algo» y se queda igual de bloqueada.
      detalle: describirCorequisitos(error.details),
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

  if (error.is("RATE_LIMIT_EXCEEDED")) {
    return {
      titulo: "Vas demasiado rápido",
      // El detalle dice CUÁNTO esperar, con el número que manda el servidor. Sin él, la
      // reacción natural es volver a pulsar enseguida, que es exactamente lo que agota el
      // límite otra vez y convierte una espera de segundos en una de minutos.
      detalle: describirEspera(error.details),
      // No se refrescan los cupos: esa consulta también cuenta contra el límite, y pedirla
      // ahora empeoraría justo lo que hay que dejar reposar.
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

  if (error instanceof ApiError && error.is("COREQUISITE_DEPENDENCY")) {
    return {
      titulo: "Otra materia tuya necesita esta",
      detalle: describirDependencia(error.details),
      refrescarCupos: false,
    };
  }

  const base = mensajeDeInscripcion(error);

  return { ...base, titulo: "No se pudo cancelar la inscripción" };
}

/**
 * Explica qué materia impide la cancelación y cómo desbloquearla.
 *
 * El rechazo tiene que ser una guía, no un muro: existe un orden que funciona —cancelar antes
 * la materia que depende— y el mensaje es el único sitio donde la persona puede enterarse.
 */
function describirDependencia(details: Record<string, unknown>): string {
  const dependientes = details.required_by;

  if (Array.isArray(dependientes) && dependientes.length > 0) {
    const codigos = dependientes.filter((c): c is string => typeof c === "string");

    if (codigos.length > 0) {
      return (
        `${codigos.join(", ")} exige cursar esta materia al mismo tiempo. ` +
        "Cancela primero esa y vuelve a intentarlo."
      );
    }
  }

  return "Cancela primero la materia que exige cursar esta al mismo tiempo.";
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

/**
 * Enumera los correquisitos que faltan y dice qué hacer con ellos.
 *
 * El correquisito y el prerrequisito se cuentan distinto a propósito. El prerrequisito no
 * tiene solución hoy —hay que aprobarlo en otro semestre—, mientras que el correquisito se
 * arregla inscribiendo la otra materia a continuación. Un mensaje común para los dos tendría
 * que ser vago en los dos casos.
 */
function describirCorequisitos(details: Record<string, unknown>): string {
  const faltantes = details.missing_corequisites;

  if (Array.isArray(faltantes) && faltantes.length > 0) {
    const codigos = faltantes.filter((c): c is string => typeof c === "string");

    if (codigos.length > 0) {
      return (
        `Inscribe también, en este mismo período: ${codigos.join(", ")}. ` +
        "Puedes hacerlo ahora y volver a intentarlo."
      );
    }
  }

  return "Consulta la ficha de la materia para ver qué debes inscribir al mismo tiempo.";
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

/**
 * Traduce la espera del limitador a algo accionable.
 *
 * El servidor manda `window_seconds`, que es la ventana completa; la espera real está en la
 * cabecera `Retry-After` y puede ser menor. Se redondea hacia arriba a propósito: decir «espera
 * menos de lo que hay que esperar» hace que la siguiente pulsación vuelva a fallar.
 */
function describirEspera(details: Record<string, unknown>): string {
  const segundos = typeof details.window_seconds === "number" ? details.window_seconds : 60;

  return (
    `Hiciste demasiadas operaciones seguidas. Espera ${segundos} segundos y vuelve a ` +
    "intentarlo; tu inscripción anterior no se perdió."
  );
}
