/**
 * Aviso destacado: error, advertencia o confirmación.
 *
 * El `role` no es decorativo. Un mensaje que aparece tras enviar un formulario no lo ve quien
 * usa lector de pantalla, salvo que se anuncie: `role="alert"` interrumpe para leerlo, y es lo
 * correcto cuando la operación ha fallado y hay que actuar.
 */

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tono = "error" | "advertencia" | "info" | "exito";

const TONOS: Record<Tono, string> = {
  error: "bg-danger-50 border-danger-600/25 text-danger-700",
  advertencia: "bg-warning-50 border-warning-600/25 text-warning-700",
  info: "bg-brand-50 border-brand-600/20 text-brand-800",
  exito: "bg-success-50 border-success-600/25 text-success-700",
};

interface AlertProps {
  tono?: Tono;
  titulo?: string;
  children: ReactNode;
  className?: string;
}

export function Alert({ tono = "error", titulo, children, className }: AlertProps) {
  return (
    <div
      // Los fallos interrumpen; el resto se lee cuando toque, sin cortar lo que se estuviera
      // anunciando.
      role={tono === "error" ? "alert" : "status"}
      className={cn("rounded-lg border px-4 py-3 text-sm", TONOS[tono], className)}
    >
      {titulo && <p className="mb-0.5 font-semibold">{titulo}</p>}
      <div>{children}</div>
    </div>
  );
}
