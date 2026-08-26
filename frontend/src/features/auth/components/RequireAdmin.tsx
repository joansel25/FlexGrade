/**
 * Guardián de las rutas de administración.
 *
 * NO ES SEGURIDAD, igual que `RequireAuth`. Lo que protege de verdad los endpoints es
 * `require_admin` en el backend, declarado una sola vez en el router y no endpoint por endpoint.
 * Esto es honestidad de la interfaz: sin él, un estudiante que escriba `/admin` en la barra vería
 * un panel vacío llenándose de errores 403 y no entendería por qué.
 *
 * Se apoya en `usuario.role`, que llega en el login **y en el refresco**. Que llegue en el
 * refresco es la condición para que esto funcione: es la llamada que restaura la sesión al
 * recargar la página, y hasta la iteración 8.1 no devolvía la cuenta. Con el rol perdido, este
 * guardián habría expulsado a un administrador legítimo en cuanto refrescara la pestaña.
 */

import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { Alert } from "@/components/ui";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import { useAuth } from "@/features/auth/useAuth";

export function RequireAdmin({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <SoloAdministracion>{children}</SoloAdministracion>
    </RequireAuth>
  );
}

/**
 * Comprueba el rol, dando por hecho que ya hay sesión.
 *
 * Va envuelto en `RequireAuth` y no en paralelo: sin sesión hay que mandar al login conservando
 * la ruta pedida, y sin rol hay que explicar que la cuenta no tiene permiso. Son dos respuestas
 * distintas, y resolverlas en el orden correcto evita mostrar «no tienes permiso» a quien
 * simplemente no ha entrado todavía.
 */
function SoloAdministracion({ children }: { children: ReactNode }) {
  const { usuario, estado } = useAuth();

  // La sesión está confirmada pero la cuenta aún no se ha resuelto. Es una ventana de un
  // instante; pintar el panel durante ella lo haría parpadear, y expulsar sería un falso
  // negativo.
  if (estado === "autenticado" && usuario === null) {
    return (
      <p className="text-ink-500 text-sm" role="status" aria-live="polite">
        Comprobando tus permisos…
      </p>
    );
  }

  if (usuario !== null && usuario.role !== "ADMIN") {
    return (
      <div className="space-y-4">
        <Alert tono="advertencia" titulo="Esta sección es de Registro Académico">
          Tu cuenta no tiene permisos de administración. Si crees que debería tenerlos,
          comunícate con Registro Académico.
        </Alert>
      </div>
    );
  }

  if (usuario === null) {
    // Sin sesión: `RequireAuth` ya habría redirigido, así que llegar aquí significa un estado
    // inesperado. Se manda al inicio en vez de dejar la pantalla en blanco.
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
