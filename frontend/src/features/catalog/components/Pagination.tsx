/**
 * Navegación entre páginas del catálogo.
 *
 * Se muestra siempre el total y el rango visible («21–40 de 87»), no solo los botones. Sin esa
 * referencia nadie sabe si está al principio o al final de una lista de decenas de materias.
 */

import { Button } from "@/components/ui";

interface PaginationProps {
  pagina: number;
  size: number;
  total: number;
  onCambiar: (pagina: number) => void;
  /** Bloquea los controles mientras llega la página siguiente. */
  cargando?: boolean;
}

export function Pagination({ pagina, size, total, onCambiar, cargando }: PaginationProps) {
  const ultimaPagina = Math.max(1, Math.ceil(total / size));

  // Con una sola página los controles no aportan nada y solo añaden ruido.
  if (total === 0 || ultimaPagina === 1) {
    return null;
  }

  const desde = (pagina - 1) * size + 1;
  const hasta = Math.min(pagina * size, total);

  return (
    <nav
      // Se etiqueta porque una página puede tener varias navegaciones: sin nombre, un lector
      // de pantalla anuncia dos «navegación» indistinguibles.
      aria-label="Paginación del catálogo"
      className="flex items-center justify-between gap-4"
    >
      <p className="text-ink-500 text-sm" aria-live="polite">
        {desde}–{hasta} de {total} materias
      </p>

      <div className="flex gap-2">
        <Button
          variante="secundario"
          tamano="sm"
          onClick={() => onCambiar(pagina - 1)}
          disabled={pagina <= 1 || cargando}
        >
          Anterior
        </Button>
        <Button
          variante="secundario"
          tamano="sm"
          onClick={() => onCambiar(pagina + 1)}
          disabled={pagina >= ultimaPagina || cargando}
        >
          Siguiente
        </Button>
      </div>
    </nav>
  );
}
