/**
 * Dónde viven los tokens de la sesión.
 *
 * DECISIÓN DELIBERADA, y la que más consecuencias tiene de esta iteración:
 *
 * - El **access token vive en memoria**, en una variable de este módulo. Es el que firma cada
 *   petición, así que es el que más daño hace si se filtra. Al no estar en `localStorage`,
 *   un script inyectado en la página no puede leerlo: no hay ninguna API del navegador que
 *   entregue el contenido de una variable de módulo.
 * - El **refresh token vive en `localStorage`**. Si también estuviera en memoria, recargar la
 *   pestaña cerraría la sesión, y en una ventana de matrícula eso significa volver a escribir
 *   la contraseña con el cronómetro corriendo.
 *
 * La alternativa impecable es una cookie `httpOnly`, que el JavaScript de la página no puede
 * leer en absoluto. Se descartó por el despliegue: el frontend se sirve desde Front Door y la
 * API desde el balanceador, dominios distintos, así que la cookie sería de terceros —bloqueada
 * por defecto en Safari y Firefox— salvo montando ambos bajo el mismo dominio con un
 * comportamiento de origen compartido. Si algún día se unifican los dominios, este módulo es
 * el único archivo que hay que reescribir.
 *
 * Consecuencia asumida: quien logre inyectar un script puede robar el refresh token y renovar
 * sesiones. Mitigado porque la API lo rota en cada refresco y porque no expone datos sensibles
 * por sí mismo, pero conviene tenerlo escrito y no descubrirlo en una auditoría.
 */

/** Clave del refresh token. Lleva versión para poder invalidar sesiones viejas si cambia. */
const CLAVE_REFRESH = "flexgrade:v1:refresh_token";

/**
 * El access token, solo en memoria.
 *
 * Se pierde al recargar, y eso es lo correcto: se recupera con el refresh token al arrancar.
 */
let accessTokenEnMemoria: string | null = null;

/** Devuelve el access token vigente, o `null` si no hay sesión activa en esta pestaña. */
export function leerAccessToken(): string | null {
  return accessTokenEnMemoria;
}

/** Guarda el access token de la sesión. */
export function guardarAccessToken(token: string | null): void {
  accessTokenEnMemoria = token;
}

/**
 * Devuelve el refresh token persistido.
 *
 * Toda lectura va envuelta en `try`: en modo privado de Safari, o con el almacenamiento del
 * sitio bloqueado, `localStorage` lanza en vez de devolver `null`. Sin la guarda, la
 * aplicación entera fallaría al arrancar en esos navegadores.
 */
export function leerRefreshToken(): string | null {
  try {
    return window.localStorage.getItem(CLAVE_REFRESH);
  } catch {
    return null;
  }
}

/** Persiste el refresh token, o lo borra si se pasa `null`. */
export function guardarRefreshToken(token: string | null): void {
  try {
    if (token === null) {
      window.localStorage.removeItem(CLAVE_REFRESH);
      return;
    }

    window.localStorage.setItem(CLAVE_REFRESH, token);
  } catch {
    // Sin persistencia la sesión dura lo que la pestaña. Es una degradación aceptable:
    // preferible a impedir el acceso a quien tiene el almacenamiento bloqueado.
  }
}

/** Borra los dos tokens. Es lo que hace efectivo el cierre de sesión en el cliente. */
export function limpiarTokens(): void {
  accessTokenEnMemoria = null;
  guardarRefreshToken(null);
}
