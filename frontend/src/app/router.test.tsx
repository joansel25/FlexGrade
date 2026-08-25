/**
 * Pruebas de la estructura de la aplicación.
 *
 * Verifican lo que se rompe en silencio: que el layout aporta sus puntos de referencia, que el
 * enlace para saltar al contenido existe y que una URL inexistente muestra el 404 en vez de una
 * página en blanco.
 *
 * Se montan sobre `/login` porque desde la iteración 5.2 es la única ruta pública, y lo que se
 * comprueba aquí es el ARMAZÓN, no qué pantalla hay dentro. La protección de rutas tiene sus
 * propias pruebas en `features/auth/sesion.test.tsx`.
 */

import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { renderConProveedores } from "@/test/render";

describe("estructura de la aplicación", () => {
  it("envuelve cada pantalla con el layout", async () => {
    renderConProveedores(<AppRoutes />, { ruta: "/login" });

    expect(
      await screen.findByRole("heading", { name: "Iniciar sesión", level: 1 }),
    ).toBeInTheDocument();
    // Los puntos de referencia son los que permiten navegar con un lector de pantalla sin
    // tener que leerlo todo.
    expect(screen.getByRole("navigation", { name: "Navegación principal" })).toBeInTheDocument();
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("ofrece un enlace para saltar al contenido", () => {
    // Sin él, quien navega con teclado atraviesa toda la navegación en cada página.
    renderConProveedores(<AppRoutes />, { ruta: "/login" });

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
