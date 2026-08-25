/**
 * El objeto de contexto de la sesión y su tipo.
 *
 * Vive separado del proveedor por el `react-refresh`: un módulo que exporta a la vez un
 * componente y un objeto que no lo es pierde el estado en cada recarga en caliente. Durante el
 * desarrollo eso significa quedarse sin sesión cada vez que se guarda un archivo, justo la
 * molestia que la recarga en caliente existe para evitar.
 */

import { createContext } from "react";

import type { AuthenticatedUser, LoginRequest } from "@/features/auth/api/types";

/** Estado en el que se encuentra la sesión. */
export type EstadoSesion =
  /** Comprobando si hay una sesión recuperable. Nadie debe decidir nada todavía. */
  | "cargando"
  | "autenticado"
  | "anonimo";

export interface AuthContextValue {
  estado: EstadoSesion;
  usuario: AuthenticatedUser | null;
  /** Token vigente, o `null`. Lo consumen los hooks que llaman a endpoints protegidos. */
  accessToken: string | null;
  /** Autentica y deja la sesión lista. Propaga el `ApiError` para que la pantalla lo muestre. */
  iniciarSesion: (credenciales: LoginRequest) => Promise<void>;
  cerrarSesion: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
