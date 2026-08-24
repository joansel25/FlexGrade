/**
 * Utilidad para montar componentes en los tests con los proveedores reales.
 *
 * Cada test construye su PROPIO `QueryClient`, con reintentos desactivados. Compartir uno haría
 * que la caché de un test respondiera al siguiente, y los reintentos convertirían la
 * comprobación de un caso de error en una espera de varios segundos.
 */

import { QueryClient } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { AppProviders } from "@/app/providers";

export function crearQueryClientDePrueba(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

interface OpcionesRender extends Omit<RenderOptions, "wrapper"> {
  /** Ruta inicial del router en memoria. */
  ruta?: string;
}

/** Monta un componente dentro de los proveedores de la aplicación. */
export function renderConProveedores(ui: ReactElement, { ruta = "/", ...opciones }: OpcionesRender = {}) {
  const queryClient = crearQueryClientDePrueba();

  function Envoltura({ children }: { children: ReactNode }) {
    return (
      <AppProviders queryClient={queryClient}>
        <MemoryRouter initialEntries={[ruta]}>{children}</MemoryRouter>
      </AppProviders>
    );
  }

  return { queryClient, ...render(ui, { wrapper: Envoltura, ...opciones }) };
}
