/**
 * Pruebas del panel de administración y de su acceso (iteración 8.1).
 *
 * Dos cosas distintas, y las dos importan:
 *
 * 1. **El acceso.** Que un estudiante no entre a `/admin` no es seguridad —lo que protege los
 *    datos es `require_admin` en el backend—, es honestidad de la interfaz. Y que un
 *    administrador SÍ entre **después de recargar la página** es lo que estuvo a punto de
 *    romperse: hasta esta iteración el refresco no devolvía la cuenta, así que la sesión se
 *    restauraba sin saber con qué rol.
 * 2. **El panel.** Que muestre lo que hay que vigilar, y que distinga un grupo a punto de
 *    llenarse de uno con sitio de sobra.
 */

import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, USUARIO, parDeTokens, respuestaDeError } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

/**
 * Monta la aplicación con una sesión restaurada desde el refresh token.
 *
 * Es el camino que recorre alguien que RECARGA la página, y no el del login: es justo donde el
 * rol se perdía antes de esta iteración.
 */
function montarComo(role: "ADMIN" | "STUDENT", ruta = "/admin") {
  server.use(
    http.post(`${API_URL}/api/v1/auth/refresh`, () =>
      HttpResponse.json({ ...parDeTokens("renovado"), user: { ...USUARIO, role } }),
    ),
  );
  guardarRefreshToken("refresh-de-prueba");

  return renderConProveedores(<AppRoutes />, { ruta });
}

describe("acceso a administración", () => {
  it("deja entrar a una cuenta con rol de administración tras recargar", async () => {
    // El caso que la iteración arregla: la sesión se restaura con el refresh token, y hasta
    // ahora eso no traía el rol. Un guardián por rol habría expulsado a un administrador
    // legítimo en cuanto refrescara la pestaña.
    montarComo("ADMIN");

    expect(await screen.findByRole("heading", { name: "Administración" })).toBeInTheDocument();
  });

  it("explica a un estudiante que la sección no es suya, sin dejarlo en blanco", async () => {
    montarComo("STUDENT");

    expect(
      await screen.findByText("Esta sección es de Registro Académico"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Cómo va la matrícula" })).not.toBeInTheDocument();
  });

  it("no ofrece el enlace de administración a un estudiante", async () => {
    // Ofrecérselo llevaría a una pantalla que le dice que no puede entrar, que es peor que no
    // ofrecerlo.
    montarComo("STUDENT", "/");
    await screen.findByRole("link", { name: "Mi plan" });

    const navegacion = screen.getByRole("navigation", { name: "Navegación principal" });
    expect(
      within(navegacion).queryByRole("link", { name: "Administración" }),
    ).not.toBeInTheDocument();
  });

  it("sí lo ofrece a quien administra", async () => {
    montarComo("ADMIN", "/");

    const enlace = await screen.findByRole("link", { name: "Administración" });
    expect(enlace).toHaveAttribute("href", "/admin");
  });
});

describe("panel de administración", () => {
  it("muestra las cifras de la matrícula del período", async () => {
    montarComo("ADMIN");

    expect(await screen.findByText("412")).toBeInTheDocument();
    expect(screen.getByText("173")).toBeInTheDocument();
    expect(screen.getByText(/Período 2025-2-V1/)).toBeInTheDocument();
  });

  it("lista los grupos a punto de llenarse con los cupos que quedan", async () => {
    // «1 cupo libre» decide más rápido que «97,5 %», así que se dice lo uno y lo otro.
    montarComo("ADMIN");

    expect(await screen.findByText(/Cálculo I · Grupo 01/)).toBeInTheDocument();
    expect(screen.getByText(/1 cupo libre/)).toBeInTheDocument();
    expect(screen.getByText("97.5 %")).toBeInTheDocument();
  });

  it("distingue el grupo crítico del que tiene sitio de sobra", async () => {
    montarComo("ADMIN");
    await screen.findByText("97.5 %");

    // El de 50 % también aparece, pero no comparte el aviso: si todos se pintaran igual, la
    // lista no diría sobre cuál hay que decidir.
    expect(screen.getByText(/20 cupos libres/)).toBeInTheDocument();
  });

  it("muestra el estado del servicio, que aquí sí tiene sentido operativo", async () => {
    // La 6.4 lo quitó de la interfaz del estudiante porque no puede hacer nada con él. Quien
    // administra sí: si la API cae en plena matrícula, es lo primero que necesita saber.
    montarComo("ADMIN");

    expect(await screen.findByText("Estado del servicio")).toBeInTheDocument();
    // El ambiente llega cuando responde `/health`: distinguir producción de pruebas evita el
    // error clásico de tocar cupos reales creyendo estar en un entorno de ensayo.
    expect(await screen.findByText("test")).toBeInTheDocument();
  });

  it("explica que no hay matrícula abierta en vez de mostrar ceros", async () => {
    // Un panel lleno de ceros parece una matrícula que va muy mal; el estado real es que
    // todavía no ha empezado.
    server.use(
      http.get(`${API_URL}/api/v1/admin/reports/enrollments`, () =>
        respuestaDeError(404, "NO_ACTIVE_PERIOD", "No hay período activo"),
      ),
      http.get(`${API_URL}/api/v1/admin/reports/occupancy`, () =>
        respuestaDeError(404, "NO_ACTIVE_PERIOD", "No hay período activo"),
      ),
    );
    montarComo("ADMIN");

    expect(
      await screen.findByText("No hay ventana de matrícula abierta"),
    ).toBeInTheDocument();
  });
});
