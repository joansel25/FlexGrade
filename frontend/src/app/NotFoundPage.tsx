/**
 * Pantalla de ruta inexistente.
 *
 * Existe desde la primera iteración a propósito: sin ella, una URL mal escrita deja la pantalla
 * en blanco y el estudiante no sabe si la aplicación se rompió o si se equivocó al escribir.
 */

import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-md py-12 text-center">
      <p className="text-brand-600 text-sm font-semibold">Error 404</p>
      <h1 className="text-ink-900 mt-2 text-2xl font-semibold">Esta página no existe</h1>
      <p className="text-ink-600 mt-3">
        Puede que el enlace esté mal escrito o que la página se haya movido.
      </p>
      <Link
        to="/"
        className="bg-brand-600 hover:bg-brand-700 mt-6 inline-flex h-10 items-center rounded-lg px-4 text-sm font-medium text-white transition-colors"
      >
        Volver al inicio
      </Link>
    </div>
  );
}
