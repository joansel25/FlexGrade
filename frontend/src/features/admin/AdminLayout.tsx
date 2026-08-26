/**
 * Armazón de las pantallas de administración.
 *
 * Va DENTRO del layout general, no en su lugar. Duplicar la cabecera, el pie, el enlace de salto
 * al contenido y el menú de la cuenta para cambiar solo la navegación sería copiar cuatro
 * decisiones de accesibilidad que ya están tomadas, y el día que una cambie habría que
 * acordarse de las dos copias.
 *
 * Lo que sí es propio es la navegación: quien administra no recorre el catálogo ni su horario,
 * recorre períodos, grupos y reportes. Mezclar los dos conjuntos de enlaces obligaría a leer
 * ocho para encontrar uno.
 *
 * El `aria-label` de este `nav` no es opcional: hay dos landmarks de navegación en la página, y
 * sin nombrarlos un lector de pantalla los anuncia como «navegación» y «navegación».
 */

import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { cn } from "@/lib/cn";

/**
 * Las secciones de administración, en el orden en que se recorren al preparar un semestre:
 * primero se abre la ventana, luego existen las materias, y solo entonces se les abre grupo.
 *
 * La de 8.4 no se declara todavía: un enlace a una pantalla que no existe es peor que su
 * ausencia, porque promete algo y lleva a un 404.
 */
const SECCIONES = [
  { a: "/admin", etiqueta: "Panel", exacto: true },
  { a: "/admin/periodos", etiqueta: "Ventanas", exacto: false },
  { a: "/admin/materias", etiqueta: "Materias", exacto: false },
  { a: "/admin/grupos", etiqueta: "Grupos", exacto: false },
  { a: "/admin/planes", etiqueta: "Planes", exacto: false },
  { a: "/admin/espacios", etiqueta: "Espacios", exacto: false },
] as const;

export function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <div className="space-y-6">
      <div className="border-ink-200 flex flex-col gap-3 border-b pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-ink-500 text-xs font-medium tracking-wide uppercase">
            Registro Académico
          </p>
          <h1 className="text-ink-900 text-2xl font-semibold tracking-tight">Administración</h1>
        </div>

        <nav aria-label="Navegación de administración">
          <ul className="flex flex-wrap items-center gap-1">
            {SECCIONES.map((seccion) => (
              <li key={seccion.a}>
                <NavLink
                  to={seccion.a}
                  end={seccion.exacto}
                  className={({ isActive }) =>
                    cn(
                      "block rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-brand-50 text-brand-700"
                        : "text-ink-600 hover:bg-ink-100 hover:text-ink-900",
                    )
                  }
                >
                  {seccion.etiqueta}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>

      {children}
    </div>
  );
}
