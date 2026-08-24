/**
 * Une clases de Tailwind condicionales.
 *
 * Sin esto, cada componente acaba con plantillas del tipo `` `base ${activo ? "x" : ""}` ``
 * que dejan espacios sueltos y clases vacías. No se usa `clsx` ni `tailwind-merge`: son dos
 * dependencias más para lo que aquí resuelven seis líneas, y este proyecto no necesita
 * resolver conflictos entre utilidades porque cada componente controla sus variantes.
 */
export function cn(...clases: Array<string | false | null | undefined>): string {
  return clases.filter(Boolean).join(" ");
}
