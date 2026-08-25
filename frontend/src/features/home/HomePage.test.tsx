/**
 * Pruebas de la pantalla de inicio (iteración 6.4).
 *
 * Comprueban las dos mitades de la limpieza: que el andamiaje de desarrollo ya no está delante
 * del estudiante, y que lo que ocupó su sitio lleva de verdad a alguna parte. Lo primero es
 * fácil de revertir sin querer —basta con que alguien vuelva a montar el componente «para
 * depurar»— y por eso se afirma en un test en vez de confiarlo al comentario del código.
 */

import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { renderConProveedores } from "@/test/render";

function montarConSesion() {
  guardarRefreshToken("refresh-de-prueba");
  return renderConProveedores(<AppRoutes />, { ruta: "/" });
}

describe("pantalla de inicio", () => {
  it("saluda por el primer nombre y muestra los datos académicos", async () => {
    montarConSesion();

    expect(await screen.findByRole("heading", { name: /Hola, /, level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Tus datos académicos")).toBeInTheDocument();
  });

  it("no muestra el estado de la API ni su ambiente ni su versión", async () => {
    // Andamiaje de la 5.1: al estudiante no le sirve —no puede hacer nada con él— y ver «test»
    // o un número de versión en la primera pantalla de su matrícula solo genera desconfianza.
    montarConSesion();
    await screen.findByText("Tus datos académicos");

    expect(screen.queryByText("Conexión con la API")).not.toBeInTheDocument();
    expect(screen.queryByText(/En línea/)).not.toBeInTheDocument();
    expect(screen.queryByText("0.1.0")).not.toBeInTheDocument();
  });

  it("lleva a las cuatro pantallas del estudiante", async () => {
    // Una pantalla de inicio que no lleva a ninguna parte obliga a buscar en la barra de
    // navegación lo que debería estar delante.
    montarConSesion();
    const accesos = await screen.findByRole("region", { name: "Qué quieres hacer" });

    const destinos = within(accesos)
      .getAllByRole("link")
      .map((enlace) => enlace.getAttribute("href"));

    expect(destinos).toEqual(["/plan", "/catalogo", "/mis-materias", "/horario"]);
  });
});
