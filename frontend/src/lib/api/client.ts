/**
 * Cliente HTTP de la API.
 *
 * Es el ÚNICO sitio del frontend que sabe que existe `fetch`, que la API vive en otro dominio y
 * que los errores llegan con la forma `{ error: { code, message } }`. Todo lo demás —hooks,
 * componentes— habla con funciones tipadas y recibe excepciones que ya significan algo.
 *
 * No se usa axios. `fetch` cubre todo lo que hace falta aquí (JSON, cancelación, cabeceras) sin
 * sumar 30 kB al bundle que descarga cada estudiante; lo que axios aporta de verdad —una capa
 * de interceptores— son las cuarenta líneas de este archivo.
 */

import { ApiError, NetworkError, esCuerpoDeError } from "@/lib/api/errors";

/**
 * URL de la API cuando se desarrolla en local sin configuración explícita.
 *
 * Coincide con el puerto que publica `docker-compose.yml`, que es donde corre el backend en
 * todas las máquinas del equipo.
 */
const API_LOCAL_POR_DEFECTO = "http://localhost:8000";

/**
 * URL base de la API, fijada en tiempo de build.
 *
 * El frontend compilado son archivos estáticos en CloudFront: no hay proceso donde leer una
 * variable de entorno al arrancar, así que Vite la incrusta al construir. Cada ambiente se
 * construye con su propio valor.
 *
 * QUÉ PASA SI FALTA. Antes se caía a cadena vacía, y el resultado era desconcertante: las
 * peticiones iban a `http://localhost:5173/health`, Vite respondía con el `index.html` de la
 * SPA, y el intento de leerlo como JSON acababa en un «Sin conexión» que señalaba al backend
 * cuando el problema era no haber copiado `.env.example` a `.env.local`.
 *
 * Ahora se distingue por ambiente, porque el fallo significa cosas distintas:
 *
 * - **En desarrollo** se usa el puerto de `docker-compose` y se avisa por consola. Que la
 *   aplicación funcione recién clonada, sin un paso previo que nadie recuerda, vale más que la
 *   pureza de exigir la variable.
 * - **En producción** se falla al arrancar. Ahí no hay valor razonable que adivinar, y una URL
 *   inventada convertiría un error de despliegue en una aplicación que parece viva pero no
 *   hace nada. Es la misma regla que sigue el backend con `DATABASE_URL`.
 */
const BASE_URL: string = resolverBaseUrl();

function resolverBaseUrl(): string {
  const configurada = import.meta.env.VITE_API_BASE_URL;

  if (configurada) {
    return configurada;
  }

  if (import.meta.env.DEV) {
    console.warn(
      `[FlexGrade] Falta VITE_API_BASE_URL; se usará ${API_LOCAL_POR_DEFECTO}. ` +
        "Copia frontend/.env.example a frontend/.env.local para fijarla.",
    );

    return API_LOCAL_POR_DEFECTO;
  }

  throw new Error(
    "VITE_API_BASE_URL no está definida. El frontend se construye con la URL de la API de su " +
      "ambiente; sin ella, la aplicación no puede hablar con el backend.",
  );
}

/**
 * Tope de espera por petición.
 *
 * Sin él, una API que no responde deja al estudiante mirando un spinner indefinido durante la
 * ventana de matrícula, sin saber si su inscripción entró. Es mejor fallar y poder reintentar.
 */
const TIMEOUT_MS = 15_000;

/** Verbos que usa la API (`API.md`). */
type Metodo = "GET" | "POST" | "PUT" | "DELETE";

export interface OpcionesPeticion {
  /** Cuerpo de la petición; se serializa como JSON. */
  body?: unknown;
  /** Token de acceso a enviar como `Authorization: Bearer`. */
  token?: string | null;
  /** Señal externa de cancelación, normalmente la que entrega TanStack Query. */
  signal?: AbortSignal;
  /** Parámetros de consulta. Los `undefined` y `null` se omiten. */
  query?: Record<string, string | number | boolean | undefined | null>;
}

/**
 * Ejecuta una petición contra la API y devuelve el cuerpo ya tipado.
 *
 * @param metodo - verbo HTTP.
 * @param ruta - ruta absoluta desde la raíz de la API, por ejemplo `/api/v1/courses`.
 * @param opciones - cuerpo, token, cancelación y parámetros de consulta.
 * @returns El cuerpo de la respuesta. Un `204 No Content` devuelve `undefined`.
 * @throws {ApiError} si el servidor respondió con un código de error del catálogo de `API.md`.
 * @throws {NetworkError} si la petición no llegó, se agotó el tiempo o la respuesta no era JSON.
 */
export async function request<T>(
  metodo: Metodo,
  ruta: string,
  opciones: OpcionesPeticion = {},
): Promise<T> {
  const { body, token, signal, query } = opciones;

  const controlador = new AbortController();
  const temporizador = setTimeout(() => {
    controlador.abort();
  }, TIMEOUT_MS);

  // Se combinan la cancelación por tiempo y la que pueda venir de fuera: TanStack Query aborta
  // las peticiones de una pantalla que el usuario ya abandonó, y esa señal debe llegar aquí.
  const abortarDesdeFuera = () => {
    controlador.abort();
  };
  signal?.addEventListener("abort", abortarDesdeFuera, { once: true });

  try {
    const respuesta = await fetch(construirUrl(ruta, query), {
      method: metodo,
      headers: construirCabeceras({ token, tieneCuerpo: body !== undefined }),
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controlador.signal,
    });

    if (!respuesta.ok) {
      throw await construirError(respuesta);
    }

    return (await leerCuerpo(respuesta)) as T;
  } catch (error) {
    // Un `ApiError` ya está interpretado: se deja pasar tal cual para que la interfaz decida
    // por su `code`. Cualquier otra cosa es un fallo de transporte.
    if (error instanceof ApiError) {
      throw error;
    }

    if (signal?.aborted) {
      // Cancelación deliberada (cambio de pantalla, nueva búsqueda). No es un fallo, y
      // convertirlo en uno pintaría un mensaje de error por navegar rápido.
      throw error;
    }

    if (error instanceof DOMException && error.name === "AbortError") {
      throw new NetworkError(
        "La solicitud tardó demasiado. Revisa tu conexión e inténtalo de nuevo.",
        error,
      );
    }

    throw new NetworkError("No se pudo contactar con el servidor.", error);
  } finally {
    clearTimeout(temporizador);
    signal?.removeEventListener("abort", abortarDesdeFuera);
  }
}

export const api = {
  get: <T>(ruta: string, opciones?: OpcionesPeticion) => request<T>("GET", ruta, opciones),
  post: <T>(ruta: string, opciones?: OpcionesPeticion) => request<T>("POST", ruta, opciones),
  put: <T>(ruta: string, opciones?: OpcionesPeticion) => request<T>("PUT", ruta, opciones),
  delete: <T>(ruta: string, opciones?: OpcionesPeticion) => request<T>("DELETE", ruta, opciones),
};

// ---------------------------------------------------------------------------
// Interno
// ---------------------------------------------------------------------------

function construirUrl(
  ruta: string,
  query?: Record<string, string | number | boolean | undefined | null>,
): string {
  const url = `${BASE_URL}${ruta}`;

  if (!query) {
    return url;
  }

  // `URLSearchParams` codifica los valores: un texto de búsqueda con `&` o espacios viaja
  // entero en vez de partir la consulta en dos.
  const parametros = new URLSearchParams();

  for (const [clave, valor] of Object.entries(query)) {
    if (valor !== undefined && valor !== null && valor !== "") {
      parametros.set(clave, String(valor));
    }
  }

  const cadena = parametros.toString();

  return cadena ? `${url}?${cadena}` : url;
}

function construirCabeceras({
  token,
  tieneCuerpo,
}: {
  token?: string | null;
  tieneCuerpo: boolean;
}): HeadersInit {
  const cabeceras: Record<string, string> = { Accept: "application/json" };

  if (tieneCuerpo) {
    cabeceras["Content-Type"] = "application/json";
  }

  if (token) {
    cabeceras["Authorization"] = `Bearer ${token}`;
  }

  return cabeceras;
}

/**
 * Traduce una respuesta fallida al error tipado que corresponda.
 *
 * Si el cuerpo no tiene la forma del contrato —un 502 del balanceador, una página HTML de
 * error— se construye igualmente un `ApiError` con el estado HTTP: la interfaz siempre recibe
 * algo con lo que decidir, nunca un `undefined` a mitad de una pantalla.
 */
async function construirError(respuesta: Response): Promise<ApiError> {
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
    message: mensajePorDefecto(respuesta.status),
  });
}

function mensajePorDefecto(status: number): string {
  if (status === 404) {
    return "No encontramos lo que buscabas.";
  }

  if (status === 422) {
    return "Revisa los datos enviados: alguno no tiene el formato esperado.";
  }

  if (status >= 500) {
    return "El servidor tuvo un problema. Inténtalo de nuevo en unos segundos.";
  }

  return "No se pudo completar la operación.";
}

async function leerCuerpo(respuesta: Response): Promise<unknown> {
  // `DELETE /enrollments/{id}` responde 204 sin cuerpo: intentar interpretarlo como JSON
  // lanzaría una excepción en una operación que salió bien.
  if (respuesta.status === 204 || respuesta.headers.get("content-length") === "0") {
    return undefined;
  }

  try {
    return await respuesta.json();
  } catch (error) {
    throw new NetworkError("La respuesta del servidor no tenía el formato esperado.", error);
  }
}
