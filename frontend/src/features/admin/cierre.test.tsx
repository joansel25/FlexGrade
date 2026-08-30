/**
 * Pruebas del cierre del semestre (iteración 9.3).
 *
 * Es la única operación IRREVERSIBLE del sistema: lo que queda en el historial decide
 * prerrequisitos y aparece en el expediente, y no hay forma de deshacerlo. Lo que se comprueba
 * aquí es que la pantalla lo trate como tal:
 *
 * - Que no ofrezca cerrar la ventana ACTIVA. El servidor lo rechaza, y ofrecerlo llevaría a un
 *   rechazo que la interfaz podía evitar.
 * - Que la confirmación diga la consecuencia real y no un «¿estás seguro?».
 * - Que el rechazo por notas pendientes nombre los grupos: sin ellos, quien cierra el semestre
 *   no sabe a qué docentes perseguir.
 */

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, USUARIO, parDeTokens } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

function montarPeriodos() {
  server.use(
    http.post(`${API_URL}/api/v1/auth/refresh`, () =>
      HttpResponse.json({ ...parDeTokens("renovado"), user: { ...USUARIO, role: "ADMIN" } }),
    ),
  );
  guardarRefreshToken("refresh-de-prueba");

  return renderConProveedores(<AppRoutes />, { ruta: "/admin/periodos" });
}

/** La tarjeta de una ventana, localizada por su botón de activar o de cerrar. */
async function tarjetaDe(codigo: string) {
  const boton = await screen.findByRole("button", { name: `Activar la ventana ${codigo}` });

  return boton.closest("li") as HTMLElement;
}

describe("cierre del semestre", () => {
  it("sobrevive a un período que llega SIN el campo consolidated_at", async () => {
    // Es el hallazgo #2 de la QA manual, fijado aquí para que no vuelva. El backend no devolvía
    // `consolidated_at` en el listado: llegaba AUSENTE, no `null`, y TypeScript no podía verlo
    // porque el tipo afirmaba lo contrario. Las consecuencias fueron dos y ninguna cosmética:
    // `consolidated_at === null` daba falso para TODAS las ventanas, así que el botón de cerrar
    // no aparecía nunca —consolidar desde la interfaz era imposible— y encima cada una anunciaba
    // «Semestre cerrado el Invalid Date».
    //
    // El doble de MSW sí declaraba el campo, y por eso ningún test lo vio: decía una verdad que
    // el servidor no decía. Este test hace lo contrario a propósito.
    server.use(
      http.get(`${API_URL}/api/v1/admin/enrollment-periods`, () =>
        HttpResponse.json({
          items: [
            {
              id: "sin-campo",
              code: "2026-1-V1",
              academic_period: "2026-1",
              name: "Ventana sin el campo",
              starts_at: "2026-01-10T08:00:00Z",
              ends_at: "2026-01-20T23:59:00Z",
              is_active: false,
            },
          ],
          total: 1,
          page: 1,
          size: 50,
        }),
      ),
    );
    montarPeriodos();

    expect(
      await screen.findByRole("button", { name: "Cerrar el semestre 2026-1-V1" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Semestre cerrado el/)).not.toBeInTheDocument();
  });

  it("dice que la fecha no se pudo leer en vez de pintar «Invalid Date»", async () => {
    // `new Date(x).toLocaleString()` devuelve la cadena «Invalid Date» ante cualquier entrada
    // que no sepa leer, y se pinta tal cual: no lanza, no avisa, y quien la ve no distingue un
    // dato corrupto de un fallo de la aplicación.
    server.use(
      http.get(`${API_URL}/api/v1/admin/enrollment-periods`, () =>
        HttpResponse.json({
          items: [
            {
              id: "fecha-rota",
              code: "2026-1-V1",
              academic_period: "2026-1",
              name: "Ventana con fecha ilegible",
              starts_at: "2026-01-10T08:00:00Z",
              ends_at: "2026-01-20T23:59:00Z",
              is_active: false,
              consolidated_at: "no-es-una-fecha",
            },
          ],
          total: 1,
          page: 1,
          size: 50,
        }),
      ),
    );
    montarPeriodos();

    expect(await screen.findByText(/no se pudo leer/)).toBeInTheDocument();
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument();
  });

  it("no ofrece cerrar la ventana que está activa", async () => {
    // El servidor lo rechaza con PERIOD_STILL_OPEN. Ofrecerlo llevaría a un rechazo que la
    // pantalla ya podía evitar.
    montarPeriodos();
    await screen.findByText("2025-2-V1");

    expect(
      screen.queryByRole("button", { name: "Cerrar el semestre 2025-2-V1" }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Cerrar el semestre 2026-1-V1" }),
    ).toBeInTheDocument();
  });

  it("la confirmación dice la consecuencia real y que no se deshace", async () => {
    // Un «¿estás seguro?» no informa de nada. Aquí lo que hay que saber es qué cambia y que no
    // hay vuelta atrás.
    const usuario = userEvent.setup();
    const tarjeta = await (montarPeriodos(), tarjetaDe("2026-1-V1"));

    await usuario.click(
      within(tarjeta).getByRole("button", { name: "Cerrar el semestre 2026-1-V1" }),
    );

    expect(within(tarjeta).getByText(/pasarán al historial académico/)).toBeInTheDocument();
    expect(within(tarjeta).getByText("No se puede deshacer.")).toBeInTheDocument();
  });

  it("nombra los grupos a los que les falta nota", async () => {
    // «Faltan notas» deja a quien cierra el semestre sin saber a quién perseguir.
    const usuario = userEvent.setup();
    const tarjeta = await (montarPeriodos(), tarjetaDe("2026-1-V1"));

    await usuario.click(
      within(tarjeta).getByRole("button", { name: "Cerrar el semestre 2026-1-V1" }),
    );
    await usuario.click(
      within(tarjeta).getByRole("button", { name: "Sí, cerrar el semestre" }),
    );

    expect(await screen.findByText("Faltan notas por poner")).toBeInTheDocument();
    expect(screen.getByText(/MAT101-01, FIS101-02/)).toBeInTheDocument();
    expect(screen.getByText(/Quedan 3 inscripciones sin calificar/)).toBeInTheDocument();
  });

  it("confirma con las cifras de lo que se escribió", async () => {
    // Es la última oportunidad de detectar que el número no cuadra: la operación no se deshace.
    server.use(
      http.post(`${API_URL}/api/v1/admin/enrollment-periods/:id/close`, () =>
        HttpResponse.json({
          period_id: "p-2026",
          period_code: "2026-1-V1",
          academic_period: "2026-1",
          consolidated_at: "2026-02-01T10:00:00Z",
          records: 42,
          approved: 31,
        }),
      ),
    );

    const usuario = userEvent.setup();
    const tarjeta = await (montarPeriodos(), tarjetaDe("2026-1-V1"));

    await usuario.click(
      within(tarjeta).getByRole("button", { name: "Cerrar el semestre 2026-1-V1" }),
    );
    await usuario.click(
      within(tarjeta).getByRole("button", { name: "Sí, cerrar el semestre" }),
    );

    expect(await screen.findByText("Semestre cerrado")).toBeInTheDocument();
    expect(screen.getByText(/42 registros/)).toBeInTheDocument();
    expect(screen.getByText(/31 de ellos aprobados/)).toBeInTheDocument();
  });

  it("explica que ya se cerró en vez de mostrar un fallo genérico", async () => {
    server.use(
      http.post(`${API_URL}/api/v1/admin/enrollment-periods/:id/close`, () =>
        HttpResponse.json(
          {
            error: {
              code: "PERIOD_ALREADY_CONSOLIDATED",
              message: "Ya se cerró",
              details: { period_id: "p-2026", consolidated_at: "2026-02-01T10:00:00Z" },
            },
          },
          { status: 409 },
        ),
      ),
    );

    const usuario = userEvent.setup();
    const tarjeta = await (montarPeriodos(), tarjetaDe("2026-1-V1"));

    await usuario.click(
      within(tarjeta).getByRole("button", { name: "Cerrar el semestre 2026-1-V1" }),
    );
    await usuario.click(
      within(tarjeta).getByRole("button", { name: "Sí, cerrar el semestre" }),
    );

    expect(await screen.findByText("Ese semestre ya se cerró")).toBeInTheDocument();
  });
});
