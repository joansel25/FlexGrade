/**
 * Indicador de estado con punto de color.
 *
 * El color por sí solo no comunica: entre el 5 % y el 8 % de los hombres no distingue verde de
 * rojo, y en un móvil bajo el sol nadie distingue nada. Por eso el punto SIEMPRE va acompañado
 * de texto, y el estado se anuncia también a los lectores de pantalla.
 */

import { cn } from "@/lib/cn";

export type Estado = "ok" | "advertencia" | "error" | "desconocido";

const COLORES: Record<Estado, string> = {
  ok: "bg-success-600",
  advertencia: "bg-warning-600",
  error: "bg-danger-600",
  desconocido: "bg-ink-300",
};

const TEXTOS: Record<Estado, string> = {
  ok: "bg-success-50 text-success-700 border-success-600/20",
  advertencia: "bg-warning-50 text-warning-700 border-warning-600/20",
  error: "bg-danger-50 text-danger-700 border-danger-600/20",
  desconocido: "bg-ink-100 text-ink-600 border-ink-200",
};

interface StatusDotProps {
  estado: Estado;
  children: string;
  /** Anima el punto mientras se está comprobando algo. */
  pulsando?: boolean;
  className?: string;
}

export function StatusDot({ estado, children, pulsando = false, className }: StatusDotProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        TEXTOS[estado],
        className,
      )}
    >
      <span
        className={cn("size-2 rounded-full", COLORES[estado], pulsando && "animate-pulse")}
        aria-hidden="true"
      />
      {children}
    </span>
  );
}
