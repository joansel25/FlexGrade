/**
 * Pruebas del indicador de estado de la API.
 *
 * Comprueban el recorrido completo —hook, cliente HTTP y respuesta simulada— en los dos casos
 * que de verdad ocurren: el servicio responde, y el servicio no está.
 */

import { screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { ServiceStatus } from "@/features/health/components/ServiceStatus";
import { API_URL } from "@/test/msw/handlers";
import { renderConProveedores } from "@/test/render";
import { server } from "@/test/msw/server";

describe("ServiceStatus", () => {
  it("muestra el ambiente cuando la API responde", async () => {
    renderConProveedores(<ServiceStatus />);

    expect(await screen.findByText(/En línea · test/)).toBeInTheDocument();
  });

  it("avisa de que no hay conexión cuando la API falla", async () => {
    server.use(http.get(`${API_URL}/health`, () => HttpResponse.error()));

    renderConProveedores(<ServiceStatus />);

    // El margen de espera es deliberado: el hook reintenta UNA vez antes de darse por vencido,
    // y ese reintento con su espera entre medias es parte del comportamiento que se prueba.
    await waitFor(() => expect(screen.getByText("Sin conexión")).toBeInTheDocument(), {
      timeout: 5000,
    });
  });
});
