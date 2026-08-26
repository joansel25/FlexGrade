/**
 * Guardián de rutas por rol.
 *
 * NO ES SEGURIDAD, igual que `RequireAuth`. Lo que protege de verdad los endpoints es
 * `require_admin` / `require_professor` en el backend, declarados una vez en cada router. Esto
 * es honestidad de la interfaz: sin él, quien escriba `/admin` en la barra vería una pantalla
 * vacía llenándose de errores 403 sin entender por qué.
 *
 * Se apoya en `usuario.role`, que llega en el login **y en el refresco**. Que llegue en el
 * refresco es la condición para que funcione: es la llamada que restaura la sesión al recargar
 * la página, y hasta la iteración 8.1 no devolvía la cuenta. Con el rol perdido, este guardián
 * habría expulsado a un administrador legítimo en cuanto refrescara la pestaña.
 */

import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { Alert } from "@/components/ui";
import type { UserRole } from "@/features/auth/api/types";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import { useAuth } from "@/features/auth/useAuth";

interface RequireRoleProps {
  rol: UserRole;
  /** Título y explicación de la negativa. Cada sección dice a quién pertenece y a quién acudir. */
  titulo: string;
  explicacion: string;
  children: ReactNode;
}

export function RequireRole({ rol, titulo, explicacion, children }: RequireRoleProps) {
  return (
    <RequireAuth>
      <SoloEsteRol rol={rol} titulo={titulo} explicacion={explicacion}>
        {children}
      </SoloEsteRol>
    </RequireAuth>
  );
}

/**
 * Comprueba el rol dando por hecho que ya hay sesión.
 *
 * Va envuelto en `RequireAuth` y no en paralelo: sin sesión hay que mandar al login conservando
 * la ruta pedida, y sin rol hay que explicar que la cuenta no tiene permiso. Son dos respuestas
 * distintas, y resolverlas en ese orden evita decirle «no tienes permiso» a quien simplemente
 * no ha entrado todavía.
 */
function SoloEsteRol({ rol, titulo, explicacion, children }: RequireRoleProps) {
  const { usuario, estado } = useAuth();

  // Sesión confirmada y cuenta aún sin resolver. Es una ventana de un instante; pintar durante
  // ella haría parpadear la pantalla, y expulsar sería un falso negativo.
  if (estado === "autenticado" && usuario === null) {
    return (
      <p className="text-ink-500 text-sm" role="status" aria-live="polite">
        Comprobando tus permisos…
      </p>
    );
  }

  if (usuario !== null && usuario.role !== rol) {
    return (
      <Alert tono="advertencia" titulo={titulo}>
        {explicacion}
      </Alert>
    );
  }

  if (usuario === null) {
    // Sin sesión: `RequireAuth` ya habría redirigido, así que llegar aquí es un estado
    // inesperado. Se manda al inicio en vez de dejar la pantalla en blanco.
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}
