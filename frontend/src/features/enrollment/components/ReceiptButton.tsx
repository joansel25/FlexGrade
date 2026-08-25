/**
 * Botón de descarga del comprobante de matrícula.
 *
 * Se muestra siempre, incluso sin materias inscritas: un comprobante vacío certifica que la
 * persona no inscribió nada, y eso es algo que a veces hay que demostrar. Ocultarlo obligaría a
 * pedirlo por ventanilla.
 */

import { useState } from "react";

import { Alert, Button } from "@/components/ui";
import { useAuth } from "@/features/auth/useAuth";
import { descargarComprobante } from "@/features/enrollment/api/receipt";
import { mensajeDeInscripcion } from "@/features/enrollment/mensajes";

export function ReceiptButton() {
  const { accessToken } = useAuth();
  const [descargando, setDescargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function descargar() {
    if (accessToken === null) {
      return;
    }

    setError(null);
    setDescargando(true);

    try {
      await descargarComprobante(accessToken);
    } catch (fallo) {
      // Se reutiliza el traductor de errores de la inscripción: los códigos son los mismos
      // (sesión expirada, sin período activo) y explicarlos dos veces acabaría en dos
      // redacciones distintas para la misma situación.
      setError(mensajeDeInscripcion(fallo).detalle);
    } finally {
      setDescargando(false);
    }
  }

  return (
    <div className="space-y-2">
      <Button
        variante="secundario"
        onClick={() => void descargar()}
        cargando={descargando}
        disabled={accessToken === null}
      >
        {descargando ? "Generando…" : "Descargar comprobante (PDF)"}
      </Button>

      {error && <Alert tono="error">{error}</Alert>}
    </div>
  );
}
