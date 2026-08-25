/**
 * Una materia en el listado del catálogo.
 *
 * La tarjeta entera es un enlace, no una tarjeta con un enlace dentro. Es lo que hace que el
 * área de pulsación sea grande en un móvil —donde se matricula la mayoría— y que el teclado
 * llegue al destino con una sola parada, en vez de tener que buscar un «Ver detalle» diminuto.
 *
 * Una materia fuera del plan de estudios sigue siendo consultable, pero se atenúa y lo dice.
 * Atenuar sin explicar sería peor que no atenuar: la persona vería una tarjeta apagada sin
 * saber si es un fallo de carga o una decisión del sistema.
 */

import { Link } from "react-router-dom";

import type { Course } from "@/features/catalog/api/types";
import { cn } from "@/lib/cn";

interface CourseCardProps {
  materia: Course;
  /** `true` si la materia no pertenece al plan de estudios del estudiante. */
  fueraDeMiPlan?: boolean;
}

export function CourseCard({ materia, fueraDeMiPlan = false }: CourseCardProps) {
  return (
    <Link
      to={`/catalogo/${materia.id}`}
      className={cn(
        "rounded-card border-ink-200 hover:border-brand-300 block border bg-white p-5 shadow-sm transition-colors hover:shadow-md",
        fueraDeMiPlan && "opacity-70",
      )}
    >
      <div className="flex items-baseline gap-2">
        <span className="bg-brand-50 text-brand-700 rounded px-2 py-0.5 font-mono text-xs font-semibold">
          {materia.code}
        </span>
        <span className="text-ink-500 text-xs">
          {/* El singular no es un detalle: «1 créditos» se lee como un descuido. */}
          {materia.credits} {materia.credits === 1 ? "crédito" : "créditos"}
        </span>
      </div>

      {fueraDeMiPlan && (
        <p className="text-ink-500 mt-2 text-xs font-medium">
          No pertenece a tu plan de estudios
        </p>
      )}

      <h3 className="text-ink-900 mt-2 text-base font-semibold">{materia.name}</h3>

      {materia.description && (
        // Dos líneas como máximo: las descripciones del catálogo tienen longitudes muy
        // distintas, y sin recorte la rejilla queda con tarjetas de alturas dispares.
        <p className="text-ink-600 mt-1.5 line-clamp-2 text-sm">{materia.description}</p>
      )}
    </Link>
  );
}
