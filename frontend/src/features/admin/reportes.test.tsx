/**
 * Pruebas de la pantalla de reportes (iteración 8.4).
 *
 * Lo que se comprueba es lo que la pantalla **decide**, no que pinte barras:
 *
 * - Que distinga los grupos a punto de llenarse de los que van holgados. Pintarlos todos igual
 *   convierte el reporte en una lista y no en una alerta.
 * - Que la tabla acompañe siempre al gráfico: es lo que se puede leer con un lector de pantalla
 *   y lo que se copia a un informe.
 * - Que el CSV salga de los datos que están en pantalla y no de un segundo viaje al servidor,
 *   que devolvería cifras distintas porque los reportes se calculan en vivo.
 */

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, USUARIO, parDeTokens } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

function montarReportes() {
  server.use(
    http.post(`${API_URL}/api/v1/auth/refresh`, () =>
      HttpResponse.json({ ...parDeTokens("renovado"), user: { ...USUARIO, role: "ADMIN" } }),
    ),
  );
  guardarRefreshToken("refresh-de-prueba");

  return renderConProveedores(<AppRoutes />, { ruta: "/admin/reportes" });
}

describe("reportes", () => {
  it("muestra los totales del período", async () => {
    montarReportes();

    expect(await screen.findByText("412")).toBeInTheDocument();
    expect(screen.getByText("173")).toBeInTheDocument();
    expect(screen.getByText("19")).toBeInTheDocument();
  });

  it("acompaña cada gráfico con su tabla de cifras", async () => {
    // El gráfico va `aria-hidden`: una barra no se puede leer. La tabla es lo que queda.
    montarReportes();

    const filaDelPrograma = await screen.findByRole("rowheader", {
      name: /Ingeniería de Sistemas/,
    });
    expect(within(filaDelPrograma.closest("tr") as HTMLElement).getByText(/240/)).toBeInTheDocument();
  });

  it("distingue el grupo a punto de llenarse del que va holgado", async () => {
    // 97,5 % y 50 %: si los pintara igual, el reporte sería una lista y no una alerta.
    montarReportes();

    const lleno = await screen.findByRole("rowheader", { name: /MAT101/ });
    const holgado = screen.getByRole("rowheader", { name: /MAT102/ });

    expect(within(lleno.closest("tr") as HTMLElement).getByText("98% · 39/40")).toBeInTheDocument();
    expect(
      within(holgado.closest("tr") as HTMLElement).getByText("50% · 20/40"),
    ).toBeInTheDocument();
  });

  it("pide más grupos al servidor cuando se cambia cuántos mostrar", async () => {
    // El tamaño viaja al servidor: recortar en el cliente mostraría los 5 más llenos de una
    // lista de 5, que no son los 25 más llenos del período.
    const pedidos: string[] = [];
    server.use(
      http.get(`${API_URL}/api/v1/admin/reports/occupancy`, ({ request }) => {
        pedidos.push(new URL(request.url).searchParams.get("size") ?? "");
        return HttpResponse.json({
          period_code: "2025-2-V1",
          generated_at: "2025-11-16T09:00:00Z",
          offerings: [],
          total: 0,
          page: 1,
          size: 25,
        });
      }),
    );

    const usuario = userEvent.setup();
    montarReportes();
    await screen.findByLabelText("Cuántos grupos mostrar");

    await usuario.selectOptions(screen.getByLabelText("Cuántos grupos mostrar"), "25");

    expect(await screen.findByText("No hay grupos abiertos en este período")).toBeInTheDocument();
    expect(pedidos).toContain("25");
  });

  it("descarga el CSV con las cifras que hay en pantalla", async () => {
    // Sin URL.createObjectURL en happy-dom: se sustituye para poder afirmar sobre la descarga
    // sin depender de la implementación del navegador.
    const crear = vi.fn((_blob: Blob) => "blob:falso");
    Object.assign(URL, { createObjectURL: crear, revokeObjectURL: vi.fn() });

    const usuario = userEvent.setup();
    montarReportes();
    const botones = await screen.findAllByRole("button", { name: "Descargar CSV" });

    await usuario.click(botones[0]!);

    expect(crear).toHaveBeenCalledTimes(1);
    const blob = crear.mock.calls[0]![0];
    expect(await blob.text()).toContain("ISIS;Ingeniería de Sistemas;240;98");
  });

  it("no ofrece descargar un reporte vacío", async () => {
    // Un CSV con solo la cabecera se confunde con una descarga fallida.
    server.use(
      http.get(`${API_URL}/api/v1/admin/reports/enrollments`, () =>
        HttpResponse.json({
          period_code: "2025-2-V1",
          generated_at: "2025-11-16T09:00:00Z",
          totals: { total_enrollments: 0, unique_students: 0, active_offerings: 0 },
          by_program: [],
        }),
      ),
    );

    montarReportes();

    expect(await screen.findByText("Todavía no hay inscripciones")).toBeInTheDocument();
    // El primero es el de inscripciones: las dos tarjetas van en el orden en que se declaran.
    const [inscripciones] = screen.getAllByRole("button", { name: "Descargar CSV" });
    expect(inscripciones!).toBeDisabled();
  });
});

beforeEach(() => {
  vi.restoreAllMocks();
});
