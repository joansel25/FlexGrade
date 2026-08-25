/**
 * Traducción de los errores de autenticación a mensajes para el estudiante.
 *
 * Vive aparte del componente porque es una decisión de producto, no de presentación: qué se le
 * cuenta a alguien cuando no puede entrar. Tenerlo en un solo sitio evita que la misma
 * situación se explique de tres formas distintas según la pantalla.
 *
 * Regla de seguridad que se aplica aquí: ante credenciales incorrectas NO se distingue si el
 * error fue el correo o la contraseña. Decir «ese correo no existe» convierte el formulario en
 * una herramienta para averiguar qué cuentas hay registradas.
 */

import { ApiError, NetworkError } from "@/lib/api/errors";

/** Mensaje que se muestra ante un fallo al iniciar sesión. */
export function mensajeDeError(error: unknown): string {
  if (error instanceof NetworkError) {
    return error.message;
  }

  if (!(error instanceof ApiError)) {
    return "Ocurrió un problema inesperado. Inténtalo de nuevo.";
  }

  if (error.is("INVALID_CREDENTIALS")) {
    return "El correo o la contraseña no son correctos.";
  }

  if (error.is("USER_INACTIVE")) {
    return "Tu cuenta está desactivada. Comunícate con Registro Académico.";
  }

  if (error.is("STUDENT_PROFILE_NOT_FOUND")) {
    return "Tu cuenta no tiene un perfil académico asociado. Comunícate con Registro Académico.";
  }

  if (error.status === 422) {
    return "Revisa el correo y la contraseña: alguno no tiene el formato esperado.";
  }

  if (error.status >= 500) {
    return "El servidor no está disponible en este momento. Inténtalo en unos segundos.";
  }

  // Como último recurso se usa el mensaje del servidor: si el backend añade un código que esta
  // versión del frontend no conoce, es preferible mostrar su explicación que un texto genérico.
  return error.message;
}
