/**
 * Campo de texto con etiqueta, ayuda y error.
 *
 * La etiqueta va SIEMPRE asociada al campo por `id`, no como texto encima. Es lo que hace que
 * pulsar sobre "Correo institucional" enfoque el campo, y lo que permite a un lector de
 * pantalla anunciar qué se está pidiendo. Un `placeholder` no sustituye a una etiqueta:
 * desaparece al escribir, justo cuando alguien podría necesitar releer qué iba ahí.
 */

import { useId, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  etiqueta: string;
  /** Texto de apoyo bajo el campo. Se oculta cuando hay un error, para no competir con él. */
  ayuda?: string;
  /** Mensaje de error del campo. Su presencia marca el campo como inválido. */
  error?: string;
}

export function TextField({ etiqueta, ayuda, error, className, ...props }: TextFieldProps) {
  // `useId` genera identificadores estables y únicos incluso con el componente repetido en la
  // misma pantalla. Inventarlos a mano acaba en dos campos con el mismo `id`, y entonces la
  // etiqueta del segundo enfoca el primero.
  const id = useId();
  const idAyuda = `${id}-ayuda`;
  const idError = `${id}-error`;

  const invalido = Boolean(error);

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-ink-700 block text-sm font-medium">
        {etiqueta}
      </label>

      <input
        id={id}
        // `aria-invalid` comunica el estado de error a quien no ve el borde rojo.
        aria-invalid={invalido || undefined}
        // Enlaza el mensaje con el campo: al enfocarlo, el lector lee también el error.
        aria-describedby={invalido ? idError : ayuda ? idAyuda : undefined}
        className={cn(
          "border-ink-300 h-11 w-full rounded-lg border px-3 text-sm",
          "placeholder:text-ink-400",
          "transition-colors duration-150",
          "focus:border-brand-500",
          "disabled:bg-ink-100 disabled:cursor-not-allowed",
          invalido && "border-danger-600 focus:border-danger-600",
          className,
        )}
        {...props}
      />

      {invalido ? (
        <p id={idError} className="text-danger-700 text-sm">
          {error}
        </p>
      ) : ayuda ? (
        <p id={idAyuda} className="text-ink-500 text-sm">
          {ayuda}
        </p>
      ) : null}
    </div>
  );
}
