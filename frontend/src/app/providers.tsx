/**
 * Proveedores globales de la aplicación.
 *
 * Se agrupan aquí, y no en `main.tsx`, por una razón práctica: los tests necesitan montar los
 * mismos proveedores que producción. Si vivieran en el punto de entrada, cada test tendría que
 * reconstruirlos a mano y acabaría probando una aplicación distinta de la que se despliega.
 */

import { QueryClientProvider } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { crearQueryClient } from "@/lib/query/queryClient";

interface AppProvidersProps {
  children: ReactNode;
  /** Cliente de consultas propio. Los tests pasan el suyo para aislar la caché entre casos. */
  queryClient?: QueryClient;
}

export function AppProviders({ children, queryClient }: AppProvidersProps) {
  // `useState` con función inicializadora y no una constante de módulo: así el cliente se crea
  // UNA vez por montaje y no se comparte entre tests, donde la caché de uno contaminaría al
  // siguiente y los haría depender del orden de ejecución.
  const [cliente] = useState(() => queryClient ?? crearQueryClient());

  return <QueryClientProvider client={cliente}>{children}</QueryClientProvider>;
}
