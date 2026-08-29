/**
 * Traducción de los errores de administración a algo que se pueda corregir.
 *
 * Es el mismo principio que `enrollment/mensajes.ts`, aplicado a otro público. Allí los `409`
 * son estados normales de una matrícula con miles de personas compitiendo; aquí casi todos son
 * **datos mal introducidos o una decisión que hay que revisar**, y lo que la pantalla diga
 * determina si quien administra corrige en diez segundos o abre un ticket.
 *
 * Cada mensaje trae qué pasó y qué hacer. «Error 409» no es ninguna de las dos cosas, y el
 * mensaje del servidor —pensado para leerse, no para actuar— casi nunca dice el siguiente paso.
 *
 * Se decide por `code` y nunca por el texto: `API.md` promete estables los códigos, no las
 * redacciones.
 */

import { ApiError, NetworkError } from "@/lib/api/errors";

export interface MensajeDeAdmin {
  titulo: string;
  detalle: string;
}

/** Traduce el fallo de cualquier operación de administración. */
export function mensajeDeAdmin(error: unknown): MensajeDeAdmin {
  if (error instanceof NetworkError) {
    return {
      titulo: "No se pudo contactar con el servidor",
      detalle:
        "Revisa tu conexión y vuelve a intentarlo. Comprueba antes si la operación alcanzó a " +
        "aplicarse: repetirla a ciegas podría duplicarla.",
    };
  }

  if (!(error instanceof ApiError)) {
    return {
      titulo: "Ocurrió un problema inesperado",
      detalle: "Vuelve a intentarlo en unos segundos.",
    };
  }

  const traduccion = TRADUCCIONES[error.code];

  if (traduccion !== undefined) {
    return traduccion(error);
  }

  if (error.status === 422) {
    // FastAPI valida el cuerpo antes de llegar al caso de uso. El detalle es técnico, así que
    // se resume: quien administra no tiene por qué leer un `loc` de Pydantic.
    return {
      titulo: "Hay un campo mal diligenciado",
      detalle: "Revisa los datos del formulario: alguno no cumple el formato que se espera.",
    };
  }

  return {
    titulo: "No se pudo completar la operación",
    // Último recurso: el mensaje del servidor. Si el backend añade un código que esta versión
    // no conoce, su explicación es mejor que un texto genérico.
    detalle: error.message,
  };
}

type Traductor = (error: ApiError) => MensajeDeAdmin;

const TRADUCCIONES: Record<string, Traductor> = {
  // ------------------------------------------------------- limite de peticiones
  //
  // Aquí el 429 no es un abuso: es alguien de Registro Académico cargando materias en tanda,
  // que es trabajo legítimo. El mensaje tiene que decirlo así y dar el número, o quien
  // administra creerá que rompió algo y abrirá un ticket por una espera de segundos.
  RATE_LIMIT_EXCEEDED: (error) => ({
    titulo: "Vas demasiado rápido",
    detalle:
      `Hiciste demasiadas operaciones seguidas. Espera ${segundosDeEspera(error)} segundos y ` +
      "continúa; lo que ya guardaste no se perdió.",
  }),

  // --------------------------------------------------------------- períodos
  DUPLICATE_PERIOD_CODE: () => ({
    titulo: "Ya existe una ventana con ese código",
    detalle: "Los códigos de período son únicos. Usa otro, por ejemplo añadiendo la vuelta.",
  }),
  INVALID_PERIOD_RANGE: () => ({
    titulo: "Las fechas están al revés",
    detalle: "El cierre tiene que ser posterior a la apertura.",
  }),

  // --------------------------------------------------------------- materias
  DUPLICATE_COURSE_CODE: () => ({
    titulo: "Ya existe una materia con ese código",
    detalle:
      "Los códigos se comparan en mayúsculas, así que «mat101» y «MAT101» son el mismo. " +
      "Búscala en el catálogo antes de crearla de nuevo.",
  }),

  // --------------------------------------------------------------- grupos
  DUPLICATE_OFFERING_GROUP: () => ({
    titulo: "Esa materia ya tiene un grupo con ese número",
    detalle: "Usa el siguiente número libre; el número identifica al grupo dentro de la materia.",
  }),
  OVERLAPPING_SCHEDULE: () => ({
    titulo: "El horario del grupo se cruza consigo mismo",
    detalle:
      "Dos de las franjas que indicaste caen a la vez. Un grupo no puede dictarse en dos " +
      "sitios al mismo tiempo.",
  }),
  INVALID_SCHEDULE_BLOCK: () => ({
    titulo: "Una franja no es válida",
    detalle: "La hora de fin tiene que ser posterior a la de inicio, y el día ir de lunes a domingo.",
  }),

  // --------------------------------------------------------------- cupos
  CAPACITY_BELOW_ENROLLED: (error) => ({
    titulo: "Ese cupo es menor que los inscritos",
    detalle: describirCupo(error.details),
  }),
  CONCURRENT_MODIFICATION: () => ({
    titulo: "Alguien cambió el grupo mientras decidías",
    detalle:
      "Vuelve a cargar la página para ver el cupo actual y decide sobre ese número. Repetir " +
      "el mismo valor a ciegas podría deshacer el cambio de la otra persona.",
  }),

  // ------------------------------------------------- cierre del semestre (9.3)
  PERIOD_ALREADY_CONSOLIDATED: () => ({
    titulo: "Ese semestre ya se cerró",
    detalle:
      "Sus notas están en el historial académico y no se vuelven a escribir. No hace falta " +
      "hacer nada más.",
  }),
  PERIOD_STILL_OPEN: () => ({
    titulo: "La ventana de matrícula sigue abierta",
    detalle:
      "Cerrar el semestre ahora dejaría fuera del historial a quien se matricule después, y " +
      "nadie lo notaría hasta que le faltara un prerrequisito. Espera a la fecha de cierre o " +
      "activa la ventana siguiente.",
  }),
  PERIOD_HAS_UNGRADED_ENROLLMENTS: (error) => ({
    titulo: "Faltan notas por poner",
    detalle: describirPendientes(error.details),
  }),
  ALREADY_IN_ACADEMIC_HISTORY: (error) => ({
    titulo: "Algunas materias ya están en el historial de ese semestre",
    detalle: describirYaRegistradas(error.details),
  }),

  // --------------------------------------------------------------- planes
  COURSE_REQUIRED_BY_OTHERS: (error) => ({
    titulo: "Otras materias del plan exigen esta",
    detalle: describirDependientes(error.details),
  }),

  IMPOSSIBLE_REQUIREMENT_CYCLE: (error) => ({
    titulo: "Ese requisito dejaría materias imposibles de cursar",
    detalle: describirCiclo(error.details),
  }),
  REQUIREMENT_WOULD_TRAP_ENROLLED: (error) => ({
    titulo: "Dejaría incompletos a los que ya están matriculados",
    detalle: describirAtrapados(error.details),
  }),

  // --------------------------------------------------------------- espacios
  DUPLICATE_SPACE_CODE: (error) => ({
    titulo: "Ya existe un espacio con ese código",
    detalle: describirAula(error.details, "Ya está en el inventario"),
  }),
  SPACE_NOT_FOUND: (error) => ({
    titulo: "Ese aula no está en el inventario",
    detalle: describirAula(error.details, "No encontramos"),
  }),
  SPACE_DOUBLE_BOOKED: (error) => ({
    titulo: "El aula ya está ocupada a esa hora",
    detalle: describirOcupacion(error.details),
  }),
  SPACE_CAPACITY_EXCEEDED: (error) => ({
    titulo: "El grupo no cabe en esa aula",
    detalle: describirAforo(error.details),
  }),

  // --------------------------------------------------------------- catálogo
  COURSE_NOT_FOUND: () => ({
    titulo: "La materia no existe",
    detalle: "Puede que se haya retirado del catálogo. Vuelve a cargar la lista.",
  }),
  NO_ACTIVE_PERIOD: () => ({
    titulo: "No hay ventana de matrícula activa",
    detalle: "Los grupos se abren siempre en el período activo. Activa uno antes de continuar.",
  }),
};

/**
 * Nombra las materias que dependen de la que se intenta quitar.
 *
 * Sin ellas el rechazo es un muro. Con los códigos delante, quien administra sabe qué requisito
 * retirar primero, que es la única salida.
 */
function describirDependientes(details: Record<string, unknown>): string {
  const dependientes = details.required_by;

  if (Array.isArray(dependientes) && dependientes.length > 0) {
    const codigos = dependientes.filter((c): c is string => typeof c === "string");

    if (codigos.length > 0) {
      return (
        `${codigos.join(", ")} la exigen. Quitarla borraría esos requisitos sin avisar, así ` +
        "que primero hay que retirarlos."
      );
    }
  }

  return "Retira antes los requisitos que la nombran.";
}

/**
 * Dibuja la vuelta completa del ciclo.
 *
 * «Hay un ciclo» no dice cuál de las aristas sobra. Con la vuelta delante —`MAT101 → MAT102 →
 * MAT101`— se ve de un vistazo, y quien administra sabe qué requisito quitar.
 */
function describirCiclo(details: Record<string, unknown>): string {
  const vuelta = details.cycle;

  if (Array.isArray(vuelta) && vuelta.length > 1) {
    const codigos = vuelta.filter((c): c is string => typeof c === "string");

    if (codigos.length > 1) {
      return (
        `${codigos.join(" → ")}. Para inscribir cualquiera habría que haber cursado antes otra ` +
        "de la vuelta, así que ninguna sería inscribible nunca. Quita uno de esos requisitos."
      );
    }
  }

  return "Los requisitos formarían una vuelta que ninguna de las materias podría cumplir.";
}

/**
 * Da el número de afectados y la salida, que es esperar a la siguiente ventana.
 *
 * El rechazo solo ocurre con la ventana CERRADA: con la ventana abierta el estudiante ve el
 * pendiente en su lista de inscripciones y lo resuelve él. Cerrada, no puede inscribir nada.
 */
function describirAtrapados(details: Record<string, unknown>): string {
  const cuantos = details.enrolled_count;
  const exigida = details.required_code;

  if (typeof cuantos === "number" && typeof exigida === "string") {
    return (
      `${cuantos} ${cuantos === 1 ? "persona ya está matriculada" : "personas ya están matriculadas"} ` +
      `y la ventana está cerrada, así que no podrían inscribir ${exigida} para completarlo. ` +
      "Cárgalo cuando se abra la siguiente ventana, o antes de que empiece la matrícula."
    );
  }

  return "Espera a que se abra la ventana de matrícula para cargar este correquisito.";
}

/**
 * Nombra los grupos a los que les falta nota.
 *
 * «Faltan notas» deja a quien cierra el semestre sin saber a quién perseguir. Con los códigos
 * delante, sabe con qué docentes hablar, que es el único siguiente paso posible.
 */
function describirPendientes(details: Record<string, unknown>): string {
  const cuantas = details.pending;
  const grupos = details.offerings;
  const codigos = Array.isArray(grupos)
    ? grupos.filter((g): g is string => typeof g === "string")
    : [];

  const cuenta =
    typeof cuantas === "number"
      ? `Quedan ${cuantas} ${cuantas === 1 ? "inscripción" : "inscripciones"} sin calificar. `
      : "Quedan inscripciones sin calificar. ";

  if (codigos.length === 0) {
    return `${cuenta}No hay forma de rellenar una nota que falta: un cero reprobaría a alguien por un trámite pendiente.`;
  }

  const listado = codigos.slice(0, 8).join(", ");
  const resto = codigos.length > 8 ? ` y ${codigos.length - 8} más` : "";

  return `${cuenta}En ${listado}${resto}. Habla con esos docentes: no hay forma de rellenar una nota que falta.`;
}

/** Nombra las materias que chocan, que es lo que permite revisar el caso concreto. */
function describirYaRegistradas(details: Record<string, unknown>): string {
  const materias = details.courses;
  const codigos = Array.isArray(materias)
    ? materias.filter((c): c is string => typeof c === "string")
    : [];

  if (codigos.length === 0) {
    return "Suele ocurrir con dos vueltas del mismo semestre. Revisa el historial antes de repetir el cierre.";
  }

  return (
    `${codigos.join(", ")} ya constan en ese semestre. Suele pasar cuando alguien cursó la ` +
    "misma materia en las dos vueltas de la matrícula; hay que revisar esos casos a mano."
  );
}

/** Dice cuántos hay inscritos, que es el número por debajo del cual no se puede bajar. */
function describirCupo(details: Record<string, unknown>): string {
  const inscritos = details.enrolled;

  if (typeof inscritos === "number") {
    return `El grupo tiene ${inscritos} ${inscritos === 1 ? "inscrito" : "inscritos"}. Nadie queda expulsado por un ajuste administrativo, así que el cupo no puede bajar de ahí.`;
  }

  return "El cupo no puede quedar por debajo del número de personas ya inscritas.";
}

/** Repite el código tal como se escribió: es lo que hay que corregir. */
function describirAula(details: Record<string, unknown>, prefijo: string): string {
  const codigo = details.code;

  if (typeof codigo === "string") {
    return `${prefijo} «${codigo}». Consulta la disponibilidad para ver los códigos que existen.`;
  }

  return "Consulta la disponibilidad para ver los códigos que existen.";
}

/** Nombra el grupo que ocupa el aula: sin eso, quien programa se queda buscando a ciegas. */
function describirOcupacion(details: Record<string, unknown>): string {
  const ocupa = details.occupied_by;
  const aula = typeof details.space_code === "string" ? details.space_code : "el aula";

  if (typeof ocupa === "object" && ocupa !== null) {
    const { course_code: materia, group_number: grupo } = ocupa as Record<string, unknown>;

    if (typeof materia === "string" && typeof grupo === "string") {
      return `${aula} la ocupa ${materia}, grupo ${grupo}. Elige otra aula o mueve la franja; la disponibilidad te dice cuáles están libres.`;
    }
  }

  return "Consulta la disponibilidad para esa franja y elige un aula libre.";
}

/** Da los dos números, que es lo que permite decidir si mover el grupo o bajar el cupo. */
function describirAforo(details: Record<string, unknown>): string {
  const { space_code: aula, capacity: aforo, required: pedidos } = details;

  if (typeof aula === "string" && typeof aforo === "number" && typeof pedidos === "number") {
    return `${aula} tiene aforo para ${aforo} y el grupo es de ${pedidos}. Busca un aula más grande o reduce el cupo.`;
  }

  return "Busca un aula con más aforo o reduce el cupo del grupo.";
}

/** La ventana que declara el error, con un valor por defecto si llegara sin ella. */
function segundosDeEspera(error: ApiError): number {
  return typeof error.details.window_seconds === "number" ? error.details.window_seconds : 60;
}
