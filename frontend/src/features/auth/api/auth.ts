/**
 * Llamadas a los endpoints de autenticación y perfil.
 *
 * Funciones sueltas, sin estado: quién guarda los tokens y cuándo se renuevan es asunto del
 * contexto de sesión. Aquí solo se traduce «iniciar sesión» a una petición HTTP concreta.
 */

import type {
  LoginRequest,
  LoginResponse,
  StudentProfile,
  RefreshResponse,
} from "@/features/auth/api/types";
import { api } from "@/lib/api/client";

/** Autentica con correo y contraseña. */
export function iniciarSesion(credenciales: LoginRequest, signal?: AbortSignal) {
  return api.post<LoginResponse>("/api/v1/auth/login", { body: credenciales, signal });
}

/**
 * Renueva el par de tokens.
 *
 * La API devuelve un refresh token NUEVO en cada llamada y hay que guardarlo: el anterior
 * queda atrás. Reutilizar el viejo acabaría en un `401` en el siguiente refresco, y la sesión
 * se cerraría sola sin motivo aparente.
 */
export function renovarSesion(refreshToken: string, signal?: AbortSignal) {
  return api.post<RefreshResponse>("/api/v1/auth/refresh", {
    body: { refresh_token: refreshToken },
    signal,
  });
}

/**
 * Cierra la sesión en el servidor.
 *
 * Su alcance real hoy es limitado y `API.md` lo dice sin rodeos: los JWT son autocontenidos, así
 * que el servidor no invalida nada todavía. La invalidación efectiva es que el cliente descarte
 * los tokens. Se llama igualmente para que el día que exista la lista de revocados en Redis el
 * frontend ya esté haciendo lo correcto.
 */
export function cerrarSesion(accessToken: string, signal?: AbortSignal) {
  return api.post<void>("/api/v1/auth/logout", { token: accessToken, signal });
}

/** Perfil del estudiante autenticado. El identificador sale del token, nunca de la petición. */
export function obtenerPerfil(accessToken: string, signal?: AbortSignal) {
  return api.get<StudentProfile>("/api/v1/students/me", { token: accessToken, signal });
}

/** Clave de caché del perfil. */
export const CLAVE_PERFIL = ["auth", "perfil"] as const;
