/**
 * Guardián de las rutas de administración.
 *
 * Es `RequireRole` con el rol y el texto de esta sección. Se conserva como componente propio
 * —en vez de escribir `RequireRole` en cada ruta— porque el mensaje de la negativa es parte de
 * la sección, y repetirlo en las siete rutas de `/admin` garantizaría que acaben diciendo cosas
 * distintas.
 */

import type { ReactNode } from "react";

import { RequireRole } from "@/features/auth/components/RequireRole";

export function RequireAdmin({ children }: { children: ReactNode }) {
  return (
    <RequireRole
      rol="ADMIN"
      titulo="Esta sección es de Registro Académico"
      explicacion="Tu cuenta no tiene permisos de administración. Si crees que debería tenerlos, comunícate con Registro Académico."
    >
      {children}
    </RequireRole>
  );
}
