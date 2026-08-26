/**
 * Estructura común de todas las pantallas: cabecera, contenido y pie.
 *
 * Vive en `app/` y no en `components/` porque no es una pieza reutilizable: es la forma de ESTA
 * aplicación. Los componentes de `components/ui` se usan dentro de muchas pantallas; este las
 * contiene.
 *
 * Dos decisiones de accesibilidad que no son opcionales:
 *
 * - El enlace para saltar al contenido. Sin él, quien navega con teclado tiene que atravesar
 *   toda la navegación en cada página antes de llegar a lo que vino a hacer.
 * - Los puntos de referencia (`header`, `nav`, `main`, `footer`). Un lector de pantalla permite
 *   saltar entre ellos; con `div` en su lugar, la única forma de moverse es leerlo todo.
 */

import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import type { UserRole } from "@/features/auth/api/types";

import { UserMenu } from "@/features/auth/components/UserMenu";
import { useAuth } from "@/features/auth/useAuth";
import { cn } from "@/lib/cn";

interface AppLayoutProps {
  children: ReactNode;
}

/**
 * Enlaces de la navegación principal.
 *
 * `roles` vacío significa «visible siempre, con o sin sesión». Filtrar por
 * rol y no solo por «hay sesión» dejó de ser un adorno en la Fase 9: un docente tiene sesión y
 * no tiene plan, ni catálogo que inscribir, ni materias propias. Ofrecerle esos enlaces le
 * llevaría a pantallas que responden `STUDENT_PROFILE_NOT_FOUND`, y el error parecería del
 * sistema y no del menú.
 *
 * El orden sigue el recorrido de una matrícula: primero lo que puedo cursar en la carrera, luego
 * lo que se ofrece este período, después lo inscrito y por último cuándo asistir. Lo de cada rol
 * va al final, porque es de pocos.
 */
// Anotado y no `as const`: con `as const`, `roles` sería una tupla distinta en cada entrada y
// el `includes` de abajo se estrecharía a `never`. Lo que importa aquí es que los roles sean
// válidos, no que la lista sea inmutable.
const NAVEGACION: readonly { a: string; etiqueta: string; roles: readonly UserRole[] }[] = [
  { a: "/", etiqueta: "Inicio", roles: [] },
  { a: "/plan", etiqueta: "Mi plan", roles: ["STUDENT"] },
  { a: "/catalogo", etiqueta: "Catálogo", roles: ["STUDENT"] },
  { a: "/mis-materias", etiqueta: "Mis materias", roles: ["STUDENT"] },
  { a: "/horario", etiqueta: "Horario", roles: ["STUDENT"] },
  { a: "/docencia", etiqueta: "Mis grupos", roles: ["PROFESSOR"] },
  { a: "/admin", etiqueta: "Administración", roles: ["ADMIN"] },
];

export function AppLayout({ children }: AppLayoutProps) {
  const { estado, usuario } = useAuth();
  const haySesion = estado === "autenticado";
  const enlaces = NAVEGACION.filter((enlace) => {
    if (enlace.roles.length === 0) {
      return true;
    }

    // Con sesión pero sin cuenta resuelta todavía —la ventana entre el refresco y su
    // respuesta— no se pinta nada de rol: aparecer y desaparecer se lee como un parpadeo.
    return haySesion && usuario !== null && enlace.roles.includes(usuario.role);
  });

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#contenido"
        className={cn(
          "sr-only focus:not-sr-only",
          "focus:bg-brand-600 focus:fixed focus:top-3 focus:left-3 focus:z-50",
          "focus:rounded-lg focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-white",
        )}
      >
        Saltar al contenido
      </a>

      <header className="border-ink-200 sticky top-0 z-40 border-b bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
          <Marca />

          <nav aria-label="Navegación principal" className="flex-1">
            <ul className="flex items-center gap-1">
              {enlaces.map((enlace) => (
                <li key={enlace.a}>
                  <NavLink
                    to={enlace.a}
                    className={({ isActive }) =>
                      cn(
                        "block rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-brand-50 text-brand-700"
                          : "text-ink-600 hover:bg-ink-100 hover:text-ink-900",
                      )
                    }
                  >
                    {enlace.etiqueta}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>

          {/* El indicador del estado de la API vivía aquí hasta la iteración 6.4. Se retiró por
              la misma razón que el recuadro de la pantalla de inicio: al estudiante no le sirve
              —no puede hacer nada con un punto rojo— y cuando la API falla es la operación que
              falló la que tiene que decirlo, con lo que hay que hacer al respecto. Tiene
              sentido operativo en el panel de administración de la fase 8, no aquí. */}
          <UserMenu />
        </div>
      </header>

      {/* `id` y `tabIndex` hacen que el enlace de salto funcione de verdad: sin ellos el foco
          no aterriza en el contenido y el enlace solo desplaza la página. */}
      <main id="contenido" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        {children}
      </main>

      <footer className="border-ink-200 border-t bg-white">
        <div className="text-ink-500 mx-auto flex max-w-6xl flex-col gap-1 px-4 py-6 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>FlexGrade — Sistema de Matrícula y Gestión Académica</p>
          <p>Proyecto de Computación en la Nube</p>
        </div>
      </footer>
    </div>
  );
}

function Marca() {
  return (
    <div className="flex items-center gap-2.5">
      <span
        className="bg-brand-600 flex size-9 items-center justify-center rounded-lg text-sm font-bold text-white"
        aria-hidden="true"
      >
        FG
      </span>
      <span className="text-ink-900 text-base leading-tight font-semibold">
        FlexGrade
        <span className="text-ink-500 block text-xs font-normal">Matrícula académica</span>
      </span>
    </div>
  );
}
