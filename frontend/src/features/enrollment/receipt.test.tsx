/**
 * Pruebas de la descarga del comprobante.
 *
 * Lo que importa comprobar aquí no es el PDF —se genera en el backend y se prueba allí— sino
 * las dos decisiones del cliente: que el token viaja en la CABECERA y no en la URL, y que el
 * archivo se entrega con el nombre que manda el servidor.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, respuestaDeError, sembrarInscripcion } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

/** Enlaces cuyo `click` se interceptó, para poder afirmar sobre la descarga. */
let descargas: { nombre: string; href: string }[] = [];

beforeEach(() => {
  descargas = [];

  // El entorno de pruebas no descarga archivos de verdad: se intercepta el click del enlace
  // temporal y se registra con qué nombre se habría guardado.
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    descargas.push({ nombre: this.download, href: this.href });
  });

  // `createObjectURL` no existe en el entorno de pruebas; se sustituye por una URL falsa.
  URL.createObjectURL = vi.fn(() => "blob:falso");
  URL.revokeObjectURL = vi.fn();
});

function montarConSesion() {
  guardarRefreshToken("refresh-persistido");
  return renderConProveedores(<AppRoutes />, { ruta: "/mis-materias" });
}

describe("descarga del comprobante", () => {
  it("envía el token en la cabecera, nunca en la URL", async () => {
    // Ponerlo en la URL lo dejaría escrito en el historial del navegador, en los registros del
    // balanceador y en la cabecera `Referer` de cualquier recurso externo.
    let autorizacion: string | null = null;
    let url = "";

    server.use(
      http.get(`${API_URL}/api/v1/students/me/receipt`, ({ request }) => {
        autorizacion = request.headers.get("Authorization");
        url = request.url;

        return new Response(new TextEncoder().encode("%PDF-1.4"), {
          headers: { "Content-Type": "application/pdf" },
        });
      }),
    );

    const usuario = userEvent.setup();
    sembrarInscripcion("g1");
    montarConSesion();
    await screen.findByText("Cálculo I");

    await usuario.click(screen.getByRole("button", { name: /Descargar comprobante/ }));

    await waitFor(() => {
      expect(autorizacion).toMatch(/^Bearer /);
    });
    expect(url).not.toContain("token");
  });

  it("guarda el archivo con el nombre que manda el servidor", async () => {
    // Incluye el código del estudiante y el período: quien descargue varios comprobantes a lo
    // largo del semestre podrá distinguirlos sin abrirlos.
    const usuario = userEvent.setup();
    sembrarInscripcion("g1");
    montarConSesion();
    await screen.findByText("Cálculo I");

    await usuario.click(screen.getByRole("button", { name: /Descargar comprobante/ }));

    await waitFor(() => {
      expect(descargas).toHaveLength(1);
    });
    expect(descargas[0]?.nombre).toBe("comprobante-matricula-1234567-2025-2-V1.pdf");
  });

  it("libera la URL temporal tras la descarga", async () => {
    // Cada `createObjectURL` retiene el blob hasta revocarse; sin esto, una pestaña abierta
    // toda la jornada de matrícula acumula un PDF por descarga.
    const usuario = userEvent.setup();
    sembrarInscripcion("g1");
    montarConSesion();
    await screen.findByText("Cálculo I");

    await usuario.click(screen.getByRole("button", { name: /Descargar comprobante/ }));

    await waitFor(() => {
      expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:falso");
    });
  });

  it("ofrece el comprobante aunque no haya materias inscritas", async () => {
    // Un comprobante vacío certifica que la persona no inscribió nada, y eso a veces hay que
    // demostrarlo.
    montarConSesion();

    expect(
      await screen.findByRole("button", { name: /Descargar comprobante/ }),
    ).toBeInTheDocument();
  });

  it("explica el fallo sin dejar el botón cargando", async () => {
    server.use(
      http.get(`${API_URL}/api/v1/students/me/receipt`, () =>
        respuestaDeError(404, "NO_ACTIVE_PERIOD", "No hay un período de matrícula activo"),
      ),
    );

    const usuario = userEvent.setup();
    sembrarInscripcion("g1");
    montarConSesion();
    await screen.findByText("Cálculo I");

    await usuario.click(screen.getByRole("button", { name: /Descargar comprobante/ }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Descargar comprobante/ })).toBeEnabled();
  });
});
