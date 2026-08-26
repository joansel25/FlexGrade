/**
 * Pruebas de los formularios de administración (iteración 8.2).
 *
 * El grueso no es el camino feliz. Un formulario de administración se juzga por lo que dice
 * cuando algo sale mal: quien lo usa está preparando un semestre, no depurando una API, y
 * «Error 409» le obliga a abrir un ticket donde un mensaje bien escrito le habría bastado para
 * corregir en diez segundos.
 *
 * Se comprueba además lo que el formulario NO hace: no valida las reglas de negocio por su
 * cuenta. Duplicar en el navegador que un aula esté libre o que un cupo no baje de los inscritos
 * garantizaría que un día la pantalla y el servidor discrepen.
 */

import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, USUARIO, parDeTokens, respuestaDeError } from "@/test/msw/handlers";
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

describe("ventanas de matrícula", () => {
  it("lista las ventanas y señala cuál está activa", async () => {
    montarAdmin("/admin/periodos");

    // Dentro de la SECCIÓN, no en toda la página: el formulario de arriba menciona un código de
    // ejemplo en su texto de ayuda, y buscarlo suelto lo capturaría a él.
    const seccion = await screen.findByRole("region", { name: "Ventanas de matrícula" });
    // `findByText` y no `getByText`: la sección existe desde el primer render, con su esqueleto
    // de carga, y la lista llega después.
    expect(await within(seccion).findByText(/2025-2-V1/)).toBeInTheDocument();
    expect(within(seccion).getByText("Activa")).toBeInTheDocument();
  });

  it("avisa de que la ventana nace inactiva, para que nadie la dé por abierta", async () => {
    const usuario = userEvent.setup();
    montarAdmin("/admin/periodos");
    await screen.findByLabelText("Código");

    await usuario.type(screen.getByLabelText("Código"), "2026-2-V1");
    await usuario.type(screen.getByLabelText("Semestre"), "2026-2");
    await usuario.type(screen.getByLabelText("Nombre"), "Matrícula 2026-2");
    await usuario.type(screen.getByLabelText("Apertura"), "2026-07-01T08:00");
    await usuario.type(screen.getByLabelText("Cierre"), "2026-07-15T18:00");
    await usuario.click(screen.getByRole("button", { name: "Crear ventana" }));

    expect(await screen.findByText("Ventana creada")).toBeInTheDocument();
    expect(screen.getByText(/Nace inactiva/)).toBeInTheDocument();
  });

  it("explica el código duplicado en vez de mostrar el error crudo", async () => {
    const usuario = userEvent.setup();
    montarAdmin("/admin/periodos");
    await screen.findByLabelText("Código");

    // `2025-2-V1` ya existe en el doble.
    await usuario.type(screen.getByLabelText("Código"), "2025-2-V1");
    await usuario.type(screen.getByLabelText("Semestre"), "2025-2");
    await usuario.type(screen.getByLabelText("Nombre"), "Repetida");
    await usuario.type(screen.getByLabelText("Apertura"), "2026-07-01T08:00");
    await usuario.type(screen.getByLabelText("Cierre"), "2026-07-15T18:00");
    await usuario.click(screen.getByRole("button", { name: "Crear ventana" }));

    expect(await screen.findByText("Ya existe una ventana con ese código")).toBeInTheDocument();
  });

  it("nombra la consecuencia antes de activar, no un «¿estás seguro?»", async () => {
    // Activar cambia a la vez lo que ven todos los estudiantes: es la operación más delicada de
    // administración y la confirmación tiene que decir exactamente eso.
    const usuario = userEvent.setup();
    montarAdmin("/admin/periodos");

    await usuario.click(await screen.findByRole("button", { name: /Activar la ventana 2026-1-V1/ }));

    expect(screen.getByText(/se cerrará la ventana que esté abierta ahora/)).toBeInTheDocument();
  });
});

describe("materias", () => {
  it("explica el código duplicado diciendo que no distingue mayúsculas", async () => {
    const usuario = userEvent.setup();
    montarAdmin("/admin/materias");
    await screen.findByRole("button", { name: "Crear materia" });

    await usuario.type(screen.getByLabelText("Código"), "MAT101");
    await usuario.type(screen.getByLabelText("Nombre"), "Cálculo I otra vez");
    await usuario.type(screen.getByLabelText("Créditos"), "4");
    await usuario.click(screen.getByRole("button", { name: "Crear materia" }));

    const aviso = await screen.findByText("Ya existe una materia con ese código");
    expect(aviso).toBeInTheDocument();
    expect(screen.getByText(/«mat101» y «MAT101» son el mismo/)).toBeInTheDocument();
  });

  it("muestra el catálogo COMPLETO, no solo el de una carrera", async () => {
    // Es lo contrario que en la pantalla del estudiante, y por la razón opuesta: quien
    // administra necesita ver todo lo que existe para no crear dos veces la misma materia.
    montarAdmin("/admin/materias");

    expect(await screen.findByText("Física")).toBeInTheDocument();
  });
});

describe("grupos", () => {
  it("no pide el docente, porque no hay forma de elegirlo todavía", async () => {
    // `professor_id` es opcional en la API y no existe endpoint para listar profesores: el
    // campo solo podría ser un UUID escrito a mano, y eso causa más errores de los que evita.
    montarAdmin("/admin/grupos");
    await screen.findByRole("button", { name: "Abrir grupo" });

    expect(screen.queryByLabelText(/Docente/)).not.toBeInTheDocument();
  });

  it("dice qué grupo ocupa el aula cuando está doblemente reservada", async () => {
    // «El aula está ocupada» deja buscando a ciegas; con el grupo delante se sabe con quién
    // hablar. El dato viaja en los `details` del 409 desde la iteración 7.2.
    server.use(
      http.post(`${API_URL}/api/v1/admin/offerings`, () =>
        respuestaDeError(409, "SPACE_DOUBLE_BOOKED", "Aula ocupada", {
          space_code: "A-201",
          day_of_week: 1,
          start_time: "08:00",
          occupied_by: { course_code: "MAT101", group_number: "02" },
        }),
      ),
    );

    const usuario = userEvent.setup();
    montarAdmin("/admin/grupos");
    await screen.findByRole("button", { name: "Abrir grupo" });

    // Se espera a que el catálogo llegue: las opciones del selector salen de `GET /courses`.
    await screen.findByRole("option", { name: /MAT101/ });
    await usuario.selectOptions(screen.getByLabelText("Materia"), "c1");
    await usuario.type(screen.getByLabelText("Grupo"), "09");
    await usuario.type(screen.getByLabelText("Cupos"), "30");
    await usuario.click(screen.getByRole("button", { name: "Abrir grupo" }));

    expect(await screen.findByText("El aula ya está ocupada a esa hora")).toBeInTheDocument();
    expect(screen.getByText(/A-201 la ocupa MAT101, grupo 02/)).toBeInTheDocument();
  });

  it("permite añadir y quitar franjas, pero nunca quedarse sin ninguna", async () => {
    const usuario = userEvent.setup();
    montarAdmin("/admin/grupos");
    await screen.findByRole("button", { name: "Añadir franja" });

    // Con una sola franja, quitarla dejaría un grupo sin horario: el botón está deshabilitado.
    expect(screen.getByRole("button", { name: "Quitar la franja 1" })).toBeDisabled();

    await usuario.click(screen.getByRole("button", { name: "Añadir franja" }));
    expect(screen.getByRole("button", { name: "Quitar la franja 2" })).toBeEnabled();
  });

  it("dice cuántos hay inscritos cuando el cupo pedido es menor", async () => {
    const usuario = userEvent.setup();
    montarAdmin("/admin/grupos");

    const campo = await screen.findByLabelText("Cupo total de MAT101 grupo 01");
    await usuario.clear(campo);
    await usuario.type(campo, "10");
    const fila = campo.closest("li");
    await usuario.click(within(fila as HTMLElement).getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Ese cupo es menor que los inscritos")).toBeInTheDocument();
    // El número por debajo del cual no se puede bajar: nadie queda expulsado por un ajuste.
    expect(screen.getByText(/tiene 39 inscritos/)).toBeInTheDocument();
  });
});
