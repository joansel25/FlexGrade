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

  // --------------------------------------------------------------- planes
  COURSE_REQUIRED_BY_OTHERS: (error) => ({
    titulo: "Otras materias del plan exigen esta",
    detalle: describirDependientes(error.details),
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
