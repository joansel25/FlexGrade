/**
 * Pruebas del editor de requisitos del plan (iteración 8.3, fase B).
 *
 * Los requisitos son retroactivos y el plan no se versiona, así que el servidor rechaza dos
 * cambios que parecen inocuos. Lo que se comprueba aquí es que la pantalla **los explique** en
 * lugar de mostrar un «no se pudo»:
 *
 * - El **ciclo imposible** deja materias que nadie podrá inscribir jamás. Decir que hay un ciclo
 *   no basta: hace falta la vuelta entera para saber qué arista quitar.
 * - El **correquisito que atrapa** solo se rechaza con la ventana cerrada, que es cuando el
 *   estudiante no puede hacer nada. El mensaje tiene que decir cuántos y cuál es la salida.
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

function montarPlanes() {
  server.use(
    http.post(`${API_URL}/api/v1/auth/refresh`, () =>
      HttpResponse.json({ ...parDeTokens("renovado"), user: { ...USUARIO, role: "ADMIN" } }),
    ),
  );
  guardarRefreshToken("refresh-de-prueba");

  return renderConProveedores(<AppRoutes />, { ruta: "/admin/planes" });
}

/** La fila de una materia del plan, que es donde vive su editor de requisitos. */
async function filaDe(codigo: string) {
  const quitar = await screen.findByRole("button", { name: `Quitar ${codigo} del plan` });

  return quitar.closest("li") as HTMLElement;
}

describe("editor de requisitos", () => {
  it("muestra lo que ya exige una materia, con su tipo", async () => {
    // Sin esto no hay nada que editar: quien administra no puede quitar un requisito que no ve.
    const fila = await (montarPlanes(), filaDe("MAT102"));

    const requisitos = within(fila).getByRole("list", { name: "Requisitos de MAT102" });
    expect(within(requisitos).getByText("MAT101")).toBeInTheDocument();
    expect(
      within(requisitos).getByLabelText("Cómo exige MAT102 a MAT101"),
    ).toHaveValue("PREREQUISITE");
  });

  it("dice que no hay requisitos en vez de dejar el hueco vacío", async () => {
    // Una lista vacía se lee igual que una que no cargó. El texto separa las dos cosas.
    const fila = await (montarPlanes(), filaDe("MAT101"));

    expect(within(fila).getByText(/Sin requisitos/)).toBeInTheDocument();
  });

  it("no ofrece exigir una materia que ya se exige, ni la propia materia", async () => {
    // La primera se cambia con su propio selector de tipo; la segunda es un ciclo trivial.
    const fila = await (montarPlanes(), filaDe("MAT102"));

    const selector = within(fila).getByLabelText("Exigir una materia para MAT102");
    expect(within(selector).queryByRole("option", { name: /MAT101/ })).not.toBeInTheDocument();
    expect(within(selector).queryByRole("option", { name: /MAT102/ })).not.toBeInTheDocument();
  });

  it("dibuja la vuelta completa cuando el requisito cerraría un ciclo", async () => {
    // «Hay un ciclo» no dice cuál de las aristas sobra. La vuelta delante sí.
    const usuario = userEvent.setup();
    const fila = await (montarPlanes(), filaDe("MAT101"));

    await usuario.selectOptions(
      within(fila).getByLabelText("Exigir una materia para MAT101"),
      "c2",
    );
    await usuario.click(within(fila).getByRole("button", { name: "Exigir" }));

    expect(
      await screen.findByText("Ese requisito dejaría materias imposibles de cursar"),
    ).toBeInTheDocument();
    expect(screen.getByText(/MAT101 → MAT102 → MAT101/)).toBeInTheDocument();
  });

  it("dice cuántos quedarían atrapados y cuál es la salida", async () => {
    // El rechazo solo ocurre con la ventana cerrada, y por eso la salida es temporal: cargarlo
    // cuando se abra la siguiente. Un mensaje sin esa salida sería un muro.
    const usuario = userEvent.setup();
    const fila = await (montarPlanes(), filaDe("TAL101"));

    await usuario.selectOptions(
      within(fila).getByLabelText("Exigir una materia para TAL101"),
      "c1",
    );
    await usuario.selectOptions(
      within(fila).getByLabelText("Cómo exigirla para TAL101"),
      "COREQUISITE",
    );
    await usuario.click(within(fila).getByRole("button", { name: "Exigir" }));

    expect(
      await screen.findByText("Dejaría incompletos a los que ya están matriculados"),
    ).toBeInTheDocument();
    expect(screen.getByText(/12 personas ya están matriculadas/)).toBeInTheDocument();
    expect(screen.getByText(/siguiente ventana/)).toBeInTheDocument();
  });

  it("el botón de exigir no se activa sin haber elegido materia", async () => {
    const fila = await (montarPlanes(), filaDe("MAT101"));

    expect(within(fila).getByRole("button", { name: "Exigir" })).toBeDisabled();
  });
});
