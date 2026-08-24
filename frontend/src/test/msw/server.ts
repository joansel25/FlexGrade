/** Servidor de MSW para el entorno de Node en el que corre Vitest. */

import { setupServer } from "msw/node";

import { handlers } from "@/test/msw/handlers";

export const server = setupServer(...handlers);
