/**
 * Acceso al estado de la sesión.
 *
 * Vive en su propio archivo y no junto al proveedor por el `react-refresh`: un módulo que
 * exporta a la vez un componente y un hook pierde el estado en cada recarga en caliente, y
 * durante el desarrollo eso significa quedarse sin sesión cada vez que se guarda un archivo.
 * Por lo mismo, el objeto de contexto vive en `authContextObject.ts`.
 */

import { useContext } from "react";

import { AuthContext, type AuthContextValue } from "@/features/auth/authContextObject";

/**
 * Devuelve el estado de la sesión.
 *
 * @throws Si se usa fuera de `AuthProvider`. Es deliberado: un `null` silencioso haría que la
 * pantalla se comportara como si nadie hubiera iniciado sesión, que es un fallo mucho más
 * difícil de rastrear que una excepción con el nombre del hook.
 */
export function useAuth(): AuthContextValue {
  const contexto = useContext(AuthContext);

  if (contexto === null) {
    throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  }

  return contexto;
}
