/**
 * Punto de entrada del navegador.
 *
 * Contiene lo mínimo: montar React sobre el `#root` del HTML. Todo lo demás —proveedores,
 * rutas, estilos— vive en módulos propios que los tests pueden montar por separado.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { AppProviders } from "@/app/providers";
import { AppRoutes } from "@/app/router";
import "@/styles/global.css";

const contenedor = document.getElementById("root");

if (!contenedor) {
  // Falla ruidosamente en vez de dejar una pantalla en blanco sin explicación.
  throw new Error("No se encontró el elemento #root en index.html");
}

createRoot(contenedor).render(
  <StrictMode>
    <AppProviders>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AppProviders>
  </StrictMode>,
);
