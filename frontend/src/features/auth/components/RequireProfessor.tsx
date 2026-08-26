/**
 * Guardián de las rutas del docente.
 *
 * El texto de la negativa nombra a Registro Académico y no a «tu administrador»: quien da de
 * alta a un docente y le enlaza la cuenta es Registro, y mandar a otro sitio alarga el problema.
 */

import type { ReactNode } from "react";

import { RequireRole } from "@/features/auth/components/RequireRole";

export function RequireProfessor({ children }: { children: ReactNode }) {
  return (
    <RequireRole
      rol="PROFESSOR"
      titulo="Esta sección es para docentes"
      explicacion="Tu cuenta no está registrada como docente. Si dictas clase este semestre, Registro Académico puede enlazar tu cuenta con tu ficha de docente."
    >
      {children}
    </RequireRole>
  );
}
