/**
 * Guardián de las rutas que exigen sesión.
 *
 * Es la contraparte en el cliente de `require_admin` y `CurrentUserDep` del backend, con una
 * diferencia que conviene tener clara: **esto no es seguridad**. Cualquiera puede saltárselo
 * editando el JavaScript de su navegador. Lo que protege de verdad son los guardianes del
 * backend, que comprueban el token en cada petición.
 *
 * Entonces, ¿para qué existe? Para que la interfaz no mienta: sin él, alguien sin sesión vería
 * la pantalla del catálogo pintarse vacía y llenarse de errores 401 en vez de recibir una
 * invitación clara a iniciar sesión.
 */

import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "@/features/auth/useAuth";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { estado } = useAuth();
  const ubicacion = useLocation();

  // Mientras se comprueba si hay una sesión recuperable NO se decide nada. Redirigir aquí
  // mandaría al login a quien sí tiene sesión, cada vez que recarga la página.
  if (estado === "cargando") {
    return <PantallaDeCarga />;
  }

  if (estado === "anonimo") {
    return (
      <Navigate
        to="/login"
        // Se recuerda a dónde quería ir para llevarlo allí después de entrar. Sin esto,
        // alguien que abre el enlace directo a su horario acaba en la pantalla de inicio y
        // tiene que volver a navegar.
        state={{ desde: ubicacion.pathname + ubicacion.search }}
        // `replace` para que el botón de atrás no devuelva a la ruta protegida, que volvería
        // a rebotar al login en un bucle incómodo.
        replace
      />
    );
  }

  return <>{children}</>;
}

function PantallaDeCarga() {
  return (
    <div
      className="flex min-h-[50vh] items-center justify-center"
      // El estado se anuncia a los lectores de pantalla, que no ven el texto aparecer.
      role="status"
      aria-live="polite"
    >
      <p className="text-ink-500 text-sm">Verificando tu sesión…</p>
    </div>
  );
}
