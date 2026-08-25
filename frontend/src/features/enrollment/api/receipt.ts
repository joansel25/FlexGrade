/**
 * Descarga del comprobante de matrícula.
 *
 * No se usa un `<a href>` normal, y la razón es concreta: el endpoint exige
 * `Authorization: Bearer`, y un enlace del navegador no envía cabeceras. Las alternativas
 * habituales son peores: poner el token en la URL lo deja escrito en el historial, en los
 * registros del balanceador y en la cabecera `Referer` de cualquier recurso externo.
 *
 * Así que se pide con `fetch`, se recibe el PDF como binario y se dispara la descarga desde un
 * enlace temporal en memoria. El token nunca sale de las cabeceras.
 */

import { ApiError, NetworkError, esCuerpoDeError } from "@/lib/api/errors";

/** URL base de la API, resuelta igual que en el cliente HTTP. */
const BASE_URL: string = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

/** Nombre por defecto si la respuesta no trae uno. */
const NOMBRE_POR_DEFECTO = "comprobante-matricula.pdf";

/**
 * Descarga el comprobante y lo entrega al navegador.
 *
 * @param token - access token de la sesión.
 * @throws {ApiError} si el servidor rechaza la petición.
 * @throws {NetworkError} si la descarga no llega.
 */
export async function descargarComprobante(token: string): Promise<void> {
  let respuesta: Response;

  try {
    respuesta = await fetch(`${BASE_URL}/api/v1/students/me/receipt`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/pdf" },
    });
  } catch (error) {
    throw new NetworkError("No se pudo descargar el comprobante.", error);
  }

  if (!respuesta.ok) {
    throw await interpretarFallo(respuesta);
  }

  const blob = await respuesta.blob();
  const nombre = nombreDelArchivo(respuesta) ?? NOMBRE_POR_DEFECTO;

  guardar(blob, nombre);
}

/**
 * Extrae el nombre del archivo de la cabecera `Content-Disposition`.
 *
 * Se prefiere el que manda el servidor: incluye el código del estudiante y el período, así que
 * quien descargue varios comprobantes a lo largo del semestre podrá distinguirlos en su
 * carpeta sin abrirlos.
 */
function nombreDelArchivo(respuesta: Response): string | null {
  const cabecera = respuesta.headers.get("content-disposition");

  if (!cabecera) {
    return null;
  }

  const coincidencia = /filename="?([^";]+)"?/i.exec(cabecera);

  return coincidencia?.[1] ?? null;
}

/** Traduce una respuesta fallida, que aquí llega como JSON aunque se pidiera un PDF. */
async function interpretarFallo(respuesta: Response): Promise<ApiError> {
  const cuerpo: unknown = await respuesta.json().catch(() => null);

  if (esCuerpoDeError(cuerpo)) {
    return new ApiError({
      status: respuesta.status,
      code: cuerpo.error.code,
      message: cuerpo.error.message,
      details: cuerpo.error.details,
    });
  }

  return new ApiError({
    status: respuesta.status,
    code: "DOMAIN_ERROR",
    message: "No se pudo generar el comprobante.",
  });
}

/**
 * Entrega el archivo al navegador.
 *
 * La URL temporal se libera siempre: cada `createObjectURL` retiene el blob en memoria hasta
 * que se revoca, y un PDF de varios cientos de kilobytes por cada descarga se acumula en una
 * pestaña que la persona deja abierta toda la jornada de matrícula.
 */
function guardar(blob: Blob, nombre: string): void {
  const url = URL.createObjectURL(blob);

  try {
    const enlace = document.createElement("a");
    enlace.href = url;
    enlace.download = nombre;
    // Hay que insertarlo en el documento: en Firefox, un enlace fuera del árbol no dispara la
    // descarga al pulsarlo desde código.
    document.body.appendChild(enlace);
    enlace.click();
    enlace.remove();
  } finally {
    URL.revokeObjectURL(url);
  }
}
