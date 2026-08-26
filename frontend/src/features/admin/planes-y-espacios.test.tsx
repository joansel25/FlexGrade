/**
 * Pruebas del editor de planes y de la pantalla de espacios (iteración 8.3).
 *
 * Lo que se comprueba es sobre todo lo que la pantalla **impide o explica**, no lo que guarda:
 *
 * - Quitar una materia del plan parece inocuo y no lo es. La clave foránea de los requisitos
 *   apunta al plan con `ON DELETE CASCADE`, así que sacar `MAT101` borraría en silencio el
 *   requisito que la nombra. El servidor lo rechaza y aquí se muestra QUIÉN depende.
 * - Un aula sin aforo medido sigue apareciendo al pedir un mínimo. Es la decisión que la Fase 7
 *   tomó —«no sé» no es «no cabe»— y esta pantalla no puede contradecirla.
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

function montarAdmin(ruta: string) {
  server.use(
    http.post(`${API_URL}/api/v1/auth/refresh`, () =>
      HttpResponse.json({ ...parDeTokens("renovado"), user: { ...USUARIO, role: "ADMIN" } }),
    ),
  );
  guardarRefreshToken("refresh-de-prueba");

  return renderConProveedores(<AppRoutes />, { ruta });
}

describe("editor de planes de estudio", () => {
  it("elige la primera carrera sola, sin obligar a un clic", async () => {
    montarAdmin("/admin/planes");

    // La pantalla arranca mostrando algo: empezar vacía obliga a un clic para ver lo que casi
    // siempre se quiere ver.
    // Se comprueba por el botón de la fila y no por el nombre de la materia: «Cálculo I» está
    // contenido en «Cálculo II», así que buscarlo encuentra las dos.
    const seccion = await screen.findByRole("region", { name: "Materias del plan" });
    expect(
      await within(seccion).findByRole("button", { name: "Quitar MAT101 del plan" }),
    ).toBeInTheDocument();
  });

  it("dice qué materias dependen de la que se intenta quitar", async () => {
    // «No se pudo quitar» dejaría a quien administra sin saber qué corregir. Con el código
    // delante, sabe qué requisito retirar primero.
    const usuario = userEvent.setup();
    montarAdmin("/admin/planes");
    await screen.findByRole("button", { name: "Quitar MAT101 del plan" });

    await usuario.click(screen.getByRole("button", { name: "Quitar MAT101 del plan" }));

    expect(await screen.findByText("Otras materias del plan exigen esta")).toBeInTheDocument();
    expect(screen.getByText(/MAT102 la exigen/)).toBeInTheDocument();
  });

  it("no ofrece añadir una materia que ya está en el plan", async () => {
    // Añadirla nunca es lo que se quiere; para cambiarle el semestre está su propia fila.
    montarAdmin("/admin/planes");
    await screen.findByRole("button", { name: "Quitar MAT101 del plan" });

    const selector = screen.getByLabelText("Materia");
    expect(within(selector).queryByRole("option", { name: /MAT101/ })).not.toBeInTheDocument();
  });

  it("el botón de guardar solo se activa si algo cambió", async () => {
    const usuario = userEvent.setup();
    montarAdmin("/admin/planes");
    await screen.findByRole("button", { name: "Quitar MAT101 del plan" });

    const fila = screen.getByLabelText("Semestre de MAT101").closest("li") as HTMLElement;
    expect(within(fila).getByRole("button", { name: "Guardar" })).toBeDisabled();

    await usuario.clear(within(fila).getByLabelText("Semestre de MAT101"));
    await usuario.type(within(fila).getByLabelText("Semestre de MAT101"), "3");

    expect(within(fila).getByRole("button", { name: "Guardar" })).toBeEnabled();
  });
});

describe("espacios físicos", () => {
  it("consulta qué aulas están libres en una franja", async () => {
    // Es la interfaz que le faltaba a la iteración 7.3: hasta ahora la única forma de encontrar
    // un aula libre era escribir códigos en el formulario de grupos y coleccionar rechazos.
    const usuario = userEvent.setup();
    montarAdmin("/admin/espacios");
    await screen.findByRole("button", { name: "Consultar" });

    await usuario.click(screen.getByRole("button", { name: "Consultar" }));

    expect(await screen.findByText(/3 espacios libres el lunes de 08:00 a 10:00/)).toBeInTheDocument();
  });

  it("un aula sin aforo registrado sigue apareciendo al pedir un mínimo", async () => {
    // «No sé» no es «no cabe». Excluirla escondería un aula que probablemente sirve; prometer
    // que cabe sería peor. Se muestra el dato ausente y quien consulta decide.
    const usuario = userEvent.setup();
    montarAdmin("/admin/espacios");
    await screen.findByLabelText("Para cuántos");

    await usuario.type(screen.getByLabelText("Para cuántos"), "200");
    await usuario.click(screen.getByRole("button", { name: "Consultar" }));

    // En el RESULTADO de la consulta, no en el inventario de abajo, donde también sale.
    // Singular a propósito en la expresión: pidiendo aforo para 200 puede quedar un solo
    // espacio, y «espacios libres» no casaría.
    const resultado = await screen.findByText(/libres? el lunes de 08:00 a 10:00/);
    const tarjeta = resultado.closest("div") as HTMLElement;
    expect(within(tarjeta).getByText("SIN-AFORO")).toBeInTheDocument();
    expect(within(tarjeta).getAllByText("aforo sin registrar").length).toBeGreaterThan(0);
  });

  it("explica el código duplicado al dar de alta un espacio", async () => {
    const usuario = userEvent.setup();
    montarAdmin("/admin/espacios");
    await screen.findByRole("button", { name: "Dar de alta" });

    // En minúsculas: el servidor normaliza antes de comparar, así que choca con `A-201`.
    await usuario.type(screen.getByLabelText("Código"), "a-201");
    await usuario.click(screen.getByRole("button", { name: "Dar de alta" }));

    expect(await screen.findByText("Ya existe un espacio con ese código")).toBeInTheDocument();
  });

  it("muestra el inventario completo con su tipo y aforo", async () => {
    montarAdmin("/admin/espacios");

    const inventario = await screen.findByRole("region", { name: "Inventario" });
    expect(await within(inventario).findByText(/LAB-01/)).toBeInTheDocument();
    expect(within(inventario).getByText(/Laboratorio · 24 personas/)).toBeInTheDocument();
  });
});
