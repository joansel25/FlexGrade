/**
 * Marcador de carga con la forma del contenido que va a llegar.
 *
 * Se prefiere a un spinner centrado porque no mueve la página: la lista aparece donde ya estaba
 * el marcador, en vez de empujar todo hacia abajo cuando llegan los datos. Ese salto es
 * especialmente molesto en el catálogo, donde alguien puede estar a punto de pulsar un grupo.
 */

import { cn } from "@/lib/cn";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("bg-ink-200 animate-pulse rounded", className)}
      // Decorativo: el estado de carga se anuncia una sola vez, en el contenedor de la lista.
      aria-hidden="true"
    />
  );
}

/** Marcador con la forma de una tarjeta de materia. */
export function CourseCardSkeleton() {
  return (
    <div className="rounded-card border-ink-200 space-y-3 border bg-white p-5">
      <div className="flex items-center gap-2">
        <Skeleton className="h-5 w-16" />
        <Skeleton className="h-4 w-12" />
      </div>
      <Skeleton className="h-5 w-3/4" />
      <Skeleton className="h-4 w-full" />
    </div>
  );
}
