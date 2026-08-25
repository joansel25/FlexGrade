/**
 * Formato de la cuenta atrás de la ventana de matrícula.
 *
 * Vive aparte del banner por dos razones: un módulo que exporta a la vez un componente y una
 * función pierde el estado en cada recarga en caliente, y esta función la va a reutilizar el
 * flujo de inscripción de la iteración 5.4.
 */

/**
 * Convierte los segundos restantes en algo legible.
 *
 * Se redondea a la unidad mayor a propósito: nadie necesita ver «2 días, 3 horas, 14 minutos y
 * 8 segundos», y un contador al segundo genera urgencia sin aportar información. Lo que
 * importa es si quedan días u horas.
 */
export function formatearTiempoRestante(segundos: number): string {
  if (segundos <= 0) {
    return "unos instantes";
  }

  const dias = Math.floor(segundos / 86_400);

  if (dias >= 1) {
    return dias === 1 ? "1 día" : `${dias} días`;
  }

  const horas = Math.floor(segundos / 3_600);

  if (horas >= 1) {
    return horas === 1 ? "1 hora" : `${horas} horas`;
  }

  const minutos = Math.max(1, Math.floor(segundos / 60));

  return minutos === 1 ? "1 minuto" : `${minutos} minutos`;
}
