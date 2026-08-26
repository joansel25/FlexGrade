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
import { AdminHomePage } from "@/features/admin/AdminHomePage";
import { AdminLayout } from "@/features/admin/AdminLayout";
import { CoursesPage as AdminCoursesPage } from "@/features/admin/CoursesPage";
import { OfferingsPage } from "@/features/admin/OfferingsPage";
import { PeriodsPage } from "@/features/admin/PeriodsPage";
import { ReportsPage } from "@/features/admin/ReportsPage";
import { SpacesPage } from "@/features/admin/SpacesPage";
import { StudyPlansPage } from "@/features/admin/StudyPlansPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { RequireAdmin } from "@/features/auth/components/RequireAdmin";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import { CatalogPage } from "@/features/catalog/CatalogPage";
import { CourseDetailPage } from "@/features/catalog/CourseDetailPage";
import { StudyPlanPage } from "@/features/catalog/StudyPlanPage";
import { MyEnrollmentsPage } from "@/features/enrollment/MyEnrollmentsPage";
import { SchedulePage } from "@/features/enrollment/SchedulePage";
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

        <Route
          path="/plan"
          element={
            <RequireAuth>
              <StudyPlanPage />
            </RequireAuth>
          }
        />

        <Route
          path="/mis-materias"
          element={
            <RequireAuth>
              <MyEnrollmentsPage />
            </RequireAuth>
          }
        />

        <Route
          path="/horario"
          element={
            <RequireAuth>
              <SchedulePage />
            </RequireAuth>
          }
        />

        {/* Administración. Protegida por ROL, no solo por sesión: un estudiante que escriba
            `/admin` vería un panel llenándose de 403 sin entender por qué. Lo que protege de
            verdad los datos es `require_admin` en el backend; esto es honestidad de la
            interfaz. */}
        <Route
          path="/admin"
          element={
            <RequireAdmin>
              <AdminLayout>
                <AdminHomePage />
              </AdminLayout>
            </RequireAdmin>
          }
        />

        <Route
          path="/admin/periodos"
          element={
            <RequireAdmin>
              <AdminLayout>
                <PeriodsPage />
              </AdminLayout>
            </RequireAdmin>
          }
        />

        <Route
          path="/admin/materias"
          element={
            <RequireAdmin>
              <AdminLayout>
                <AdminCoursesPage />
              </AdminLayout>
            </RequireAdmin>
          }
        />

        <Route
          path="/admin/grupos"
          element={
            <RequireAdmin>
              <AdminLayout>
                <OfferingsPage />
              </AdminLayout>
            </RequireAdmin>
          }
        />

        <Route
          path="/admin/planes"
          element={
            <RequireAdmin>
              <AdminLayout>
                <StudyPlansPage />
              </AdminLayout>
            </RequireAdmin>
          }
        />

        <Route
          path="/admin/espacios"
          element={
            <RequireAdmin>
              <AdminLayout>
                <SpacesPage />
              </AdminLayout>
            </RequireAdmin>
          }
        />

        <Route
          path="/admin/reportes"
          element={
            <RequireAdmin>
              <AdminLayout>
                <ReportsPage />
              </AdminLayout>
            </RequireAdmin>
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
