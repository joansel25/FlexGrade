/**
 * Preparación común de todos los tests.
 *
 * Las tres reglas de abajo existen para que los tests sean INDEPENDIENTES entre sí. Un test que
 * pasa solo pero falla en la suite —o al revés— cuesta más tiempo de depurar que el bug que
 * intentaba evitar.
 */

import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { limpiarTokens } from "@/features/auth/tokenStorage";
import { resetearInscripciones, resetearPeriodos } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";

// El defecto de `findBy*` es 1 s, y esta suite monta el router completo en cada test. Con los
// ficheros corriendo en paralelo, una máquina cargada tarda más de un segundo en pintar una
// lista que llega de MSW, y el test falla por lentitud y no por un fallo real. Subirlo NO
// esconde nada: un test roto sigue agotando el plazo y fallando igual, solo que ahora hace
// falta que esté roto de verdad.
configure({ asyncUtilTimeout: 5000 });

beforeAll(() => {
  // `error` y no `warn`: una petición no declarada en los handlers es un test que está
  // llamando a algo que no esperaba: mejor que falle a que llegue a la red de verdad.
  server.listen({ onUnhandledRequest: "error" });
});

afterEach(() => {
  // Se descarta lo que un test haya sobrescrito con `server.use(...)`.
  server.resetHandlers();
  // Se desmonta el DOM del test anterior.
  cleanup();
  // Los tokens viven fuera de React —memoria del módulo y `localStorage`—, así que no se van
  // con el desmontaje. Sin esta limpieza, un test que inicia sesión dejaría autenticado al
  // siguiente y la suite pasaría o fallaría según el orden.
  limpiarTokens();
  // Los handlers de inscripción guardan estado entre llamadas para poder probar el
  // recorrido completo; sin este reinicio, un test empezaría con las materias del anterior.
  resetearInscripciones();
  resetearPeriodos();
});

afterAll(() => {
  server.close();
});
