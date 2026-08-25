/**
 * Estado vacío: no hay nada que mostrar, y eso no es un error.
 *
 * Un listado vacío sin explicación se lee como un fallo de carga. Este componente obliga a
 * decir DOS cosas: qué pasó y qué se puede hacer al respecto. Sin la segunda, la persona se
 * queda mirando una pantalla que no la lleva a ninguna parte.
 */

import type { ReactNode } from "react";

interface EmptyStateProps {
  titulo: string;
  descripcion: string;
  /** Acción sugerida: limpiar filtros, volver al catálogo, etc. */
  accion?: ReactNode;
}

export function EmptyState({ titulo, descripcion, accion }: EmptyStateProps) {
  return (
    <div className="border-ink-200 rounded-card border border-dashed px-6 py-12 text-center">
      <p className="text-ink-800 text-base font-medium">{titulo}</p>
      <p className="text-ink-500 mx-auto mt-1.5 max-w-md text-sm">{descripcion}</p>
      {accion && <div className="mt-5">{accion}</div>}
    </div>
  );
}
