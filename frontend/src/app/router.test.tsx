/**
 * Pruebas de la estructura de la aplicación.
 *
 * Verifican dos cosas que se rompen en silencio: que la pantalla de inicio se pinta con su
 * layout, y que una URL inexistente muestra el 404 en vez de una página en blanco.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { renderConProveedores } from "@/test/render";

describe("rutas de la aplicación", () => {
  it("muestra la pantalla de inicio dentro del layout", async () => {
    renderConProveedores(<AppRoutes />, { ruta: "/" });

    expect(
      await screen.findByRole("heading", { name: "Matrícula académica", level: 1 }),
    ).toBeInTheDocument();
    // El layout aporta los puntos de referencia que permiten navegar con lector de pantalla.
    expect(screen.getByRole("navigation", { name: "Navegación principal" })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });

  it("ofrece un enlace para saltar al contenido", () => {
    // Sin él, quien navega con teclado atraviesa toda la navegación en cada página.
    renderConProveedores(<AppRoutes />, { ruta: "/" });

    expect(screen.getByRole("link", { name: "Saltar al contenido" })).toHaveAttribute(
      "href",
      "#contenido",
    );
  });

  it("muestra la pantalla 404 ante una ruta que no existe", () => {
    renderConProveedores(<AppRoutes />, { ruta: "/ruta-que-no-existe" });

    expect(screen.getByRole("heading", { name: "Esta página no existe" })).toBeInTheDocument();
  });
});
