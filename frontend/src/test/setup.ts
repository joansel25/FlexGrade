/**
 * Preparación común de todos los tests.
 *
 * Las tres reglas de abajo existen para que los tests sean INDEPENDIENTES entre sí. Un test que
 * pasa solo pero falla en la suite —o al revés— cuesta más tiempo de depurar que el bug que
 * intentaba evitar.
 */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { limpiarTokens } from "@/features/auth/tokenStorage";
import { server } from "@/test/msw/server";

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
});

afterAll(() => {
  server.close();
});
