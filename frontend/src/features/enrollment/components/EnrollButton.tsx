/**
 * Botón de inscripción de un grupo, con su resultado.
 *
 * Es el punto donde el estudiante compite por un cupo, así que concentra tres cuidados:
 *
 * 1. **No mentir sobre la disponibilidad.** Si el grupo está lleno, el botón lo dice y no se
 *    puede pulsar. Pero si tenía cupo y lo pierde en la carrera, el `409` se explica como lo
 *    que es —«alguien se te adelantó»— con los cupos ya refrescados.
 * 2. **No permitir el doble envío.** Mientras la petición viaja, el botón queda bloqueado. Sin
 *    eso, dos pulsaciones rápidas serían dos intentos y el segundo recibiría un
 *    `ALREADY_ENROLLED` desconcertante.
 * 3. **Anunciar el resultado.** El mensaje aparece en un contenedor que los lectores de
 *    pantalla leen al cambiar, porque quien no ve la pantalla no se entera de que se inscribió.
 */

import { Alert, Button } from "@/components/ui";
import { useEnroll } from "@/features/enrollment/hooks";
import { mensajeDeInscripcion } from "@/features/enrollment/mensajes";

interface EnrollButtonProps {
  offeringId: string;
  /** Número del grupo, para que el botón diga en qué se está inscribiendo. */
  groupNumber: string;
  disponibles: number;
  /** `true` si el estudiante ya tiene inscrito ESTE grupo. */
  yaInscrito: boolean;
  /** `false` cuando la ventana de matrícula no admite inscripciones ahora mismo. */
  matriculaAbierta: boolean;
}

export function EnrollButton({
  offeringId,
  groupNumber,
  disponibles,
  yaInscrito,
  matriculaAbierta,
}: EnrollButtonProps) {
  const inscripcion = useEnroll();

  // El ORDEN de estas dos condiciones importa, y el motivo no es evidente: al inscribir con
  // éxito se invalidan las consultas, así que `yaInscrito` pasa a `true` en el mismo instante.
  // Si «ya inscrito» se comprobara primero, la confirmación desaparecería antes de que nadie
  // pudiera leerla, y la persona vería el botón cambiar de texto sin saber si funcionó.
  if (inscripcion.isSuccess) {
    return (
      <Alert tono="exito" titulo="Inscripción confirmada">
        Quedaste inscrito en {inscripcion.data.course_code}, grupo {inscripcion.data.group_number}.
      </Alert>
    );
  }

  if (yaInscrito) {
    return (
      <p className="text-success-700 text-sm font-medium" role="status">
        Ya estás inscrito en este grupo
      </p>
    );
  }

  const lleno = disponibles <= 0;
  // El motivo por el que no se puede pulsar se dice en voz alta: un botón gris sin explicación
  // deja a la persona buscando qué hizo mal.
  const motivoBloqueo = !matriculaAbierta
    ? "La matrícula no está abierta en este momento."
    : lleno
      ? "Este grupo no tiene cupos disponibles."
      : null;

  const resultado = inscripcion.isError ? mensajeDeInscripcion(inscripcion.error) : null;

  return (
    <div className="space-y-2">
      <Button
        onClick={() => inscripcion.mutate(offeringId)}
        cargando={inscripcion.isPending}
        disabled={motivoBloqueo !== null || inscripcion.isPending}
        // El nombre accesible dice de qué grupo se trata: en una lista de cinco botones
        // «Inscribir», quien usa lector de pantalla no sabría cuál está pulsando.
        aria-label={`Inscribir grupo ${groupNumber}`}
      >
        {inscripcion.isPending ? "Inscribiendo…" : "Inscribir"}
      </Button>

      {motivoBloqueo && <p className="text-ink-500 text-xs">{motivoBloqueo}</p>}

      {resultado && (
        <Alert tono="error" titulo={resultado.titulo}>
          {resultado.detalle}
        </Alert>
      )}
    </div>
  );
}
