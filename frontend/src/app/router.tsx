/**
 * Rutas de la aplicación.
 *
 * Se declaran en un solo archivo para poder responder de un vistazo a "qué pantallas existen".
 * Las rutas protegidas por sesión llegan en la iteración 5.2, envolviendo estos elementos con
 * el guardián de autenticación.
 */

import { Route, Routes } from "react-router-dom";

import { NotFoundPage } from "@/app/NotFoundPage";
import { AppLayout } from "@/app/layout/AppLayout";
import { HomePage } from "@/features/home/HomePage";

export function AppRoutes() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        {/* Comodín al final: cualquier ruta no declarada cae aquí en vez de dejar la pantalla
            en blanco. */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppLayout>
  );
}
