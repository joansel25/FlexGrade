/**
 * Botón de la aplicación.
 *
 * Es un `<button>` de verdad, no un `<div>` con un `onClick`: así responde a Enter y a Espacio,
 * el lector de pantalla lo anuncia como botón y entra en el orden de tabulación sin trabajo
 * extra. Lo mismo vale para `disabled`, que además impide el doble envío de una inscripción.
 */

import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variante = "primario" | "secundario" | "fantasma" | "peligro";
type Tamano = "sm" | "md" | "lg";

const VARIANTES: Record<Variante, string> = {
  primario: "bg-brand-600 text-white hover:bg-brand-700 active:bg-brand-800 shadow-sm",
  secundario: "bg-white text-ink-800 border border-ink-200 hover:bg-ink-50 active:bg-ink-100",
  fantasma: "bg-transparent text-brand-700 hover:bg-brand-50 active:bg-brand-100",
  peligro: "bg-danger-600 text-white hover:bg-danger-700 shadow-sm",
};

const TAMANOS: Record<Tamano, string> = {
  sm: "h-8 px-3 text-sm gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-12 px-6 text-base gap-2",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variante?: Variante;
  tamano?: Tamano;
  /** Muestra el estado de carga y bloquea el botón para evitar un segundo envío. */
  cargando?: boolean;
  children: ReactNode;
}

export function Button({
  variante = "primario",
  tamano = "md",
  cargando = false,
  className,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      // `type="button"` por defecto: dentro de un formulario, el valor implícito de HTML es
      // `submit`, y un botón de "cancelar" acabaría enviando el formulario.
      type="button"
      disabled={disabled ?? cargando}
      // Anuncia el estado de carga a quien usa lector de pantalla, que no ve el spinner.
      aria-busy={cargando || undefined}
      className={cn(
        "inline-flex items-center justify-center rounded-lg font-medium",
        "transition-colors duration-150",
        "disabled:cursor-not-allowed disabled:opacity-60",
        VARIANTES[variante],
        TAMANOS[tamano],
        className,
      )}
      {...props}
    >
      {cargando && <Spinner />}
      {children}
    </button>
  );
}

function Spinner() {
  return (
    <svg
      className="size-4 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      // Decorativo: el estado ya viaja en `aria-busy`, y anunciarlo dos veces es ruido.
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}
