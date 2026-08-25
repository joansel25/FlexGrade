/**
 * Rutas de la aplicación.
 *
 * Se declaran en un solo archivo para poder responder de un vistazo a dos preguntas: qué
 * pantallas existen y cuáles exigen sesión. Envolver cada elemento protegido con `RequireAuth`
 * —en vez de comprobarlo dentro de cada pantalla— hace que proteger sea lo visible y olvidarse
 * de hacerlo, evidente al leer este archivo.
 */

import { Route, Routes } from "react-router-dom";

import { NotFoundPage } from "@/app/NotFoundPage";
import { AppLayout } from "@/app/layout/AppLayout";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import { CatalogPage } from "@/features/catalog/CatalogPage";
import { CourseDetailPage } from "@/features/catalog/CourseDetailPage";
import { HomePage } from "@/features/home/HomePage";

export function AppRoutes() {
  return (
    <AppLayout>
      <Routes>
        {/* Pública: es la puerta de entrada, y exigir sesión aquí sería un bucle. */}
        <Route path="/login" element={<LoginPage />} />

        <Route
          path="/"
          element={
            <RequireAuth>
              <HomePage />
            </RequireAuth>
          }
        />

        <Route
          path="/catalogo"
          element={
            <RequireAuth>
              <CatalogPage />
            </RequireAuth>
          }
        />

        <Route
          path="/catalogo/:courseId"
          element={
            <RequireAuth>
              <CourseDetailPage />
            </RequireAuth>
          }
        />

        {/* Comodín al final: cualquier ruta no declarada cae aquí en vez de dejar la pantalla
            en blanco. No se protege, para que una URL mal escrita explique el error en vez de
            rebotar al login. */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppLayout>
  );
}
