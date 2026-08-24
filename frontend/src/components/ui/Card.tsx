/**
 * Tarjeta: la unidad visual con la que se presentan materias, grupos e inscripciones.
 *
 * Se define una sola vez para que todas tengan el mismo radio, borde y sombra. Una pantalla con
 * tres tarjetas ligeramente distintas se percibe como descuidada aunque cada una, por separado,
 * se vea bien.
 */

import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

export function Card({ className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-card border-ink-200 border bg-white shadow-sm",
        "transition-shadow duration-150",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className, children, ...props }: CardProps) {
  return (
    <div className={cn("border-ink-100 border-b px-5 py-4", className)} {...props}>
      {children}
    </div>
  );
}

export function CardTitle({ className, children, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h2 className={cn("text-ink-900 text-base font-semibold", className)} {...props}>
      {children}
    </h2>
  );
}

export function CardBody({ className, children, ...props }: CardProps) {
  return (
    <div className={cn("px-5 py-4", className)} {...props}>
      {children}
    </div>
  );
}
