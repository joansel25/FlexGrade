/**
 * Pruebas de la pantalla de calificación (iteración 9.2).
 *
 * Lo que se comprueba es lo que la pantalla **distingue**, que es donde está el riesgo:
 *
 * - «Sin calificar» y «0.0» son estados opuestos y con un cero por defecto se verían igual. El
 *   campo tiene que empezar vacío.
 * - Cada fila se guarda por separado. Un «guardar todo» obligaría a terminar de una sentada, y
 *   un fallo a mitad dejaría media lista guardada sin decir cuál mitad.
 * - Quien canceló la materia no se califica, y el mensaje tiene que decir eso y no un fallo
 *   genérico: es lo que pasa de verdad cuando alguien cancela después de abrir la lista.
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

function montarLista(offeringId = "g1") {
  server.use(
    http.post(`${API_URL}/api/v1/auth/refresh`, () =>
      HttpResponse.json({ ...parDeTokens("renovado"), user: { ...USUARIO, role: "PROFESSOR" } }),
    ),
  );
  guardarRefreshToken("refresh-de-prueba");

  return renderConProveedores(<AppRoutes />, { ruta: `/docencia/${offeringId}` });
}

/** La fila de una persona, que es donde vive su campo de nota. */
async function filaDe(nombre: string) {
  const campo = await screen.findByLabelText(`Nota de ${nombre}`);

  return campo.closest("li") as HTMLElement;
}

describe("lista de calificación", () => {
  it("el campo empieza vacío cuando no hay nota, no en cero", async () => {
    // Un cero de partida sería una nota, y reprobatoria: el peor valor posible para significar
    // «todavía no lo sé».
    const fila = await (montarLista(), filaDe("Beto Bernal"));

    expect(within(fila).getByLabelText("Nota de Beto Bernal")).toHaveValue(null);
    expect(within(fila).getByText("Sin calificar.")).toBeInTheDocument();
  });

  it("trae la nota ya puesta para poder corregirla", async () => {
    const fila = await (montarLista(), filaDe("Ada Álvarez"));

    expect(within(fila).getByLabelText("Nota de Ada Álvarez")).toHaveValue(4.25);
    expect(within(fila).queryByText("Sin calificar.")).not.toBeInTheDocument();
  });

  it("dice cuántas faltan y que eso bloquea el cierre del período", async () => {
    // Es lo que responde «¿ya terminé?», y esa pregunta se hace antes de recorrer la lista.
    montarLista();

    expect(await screen.findByText("Quedan notas por poner")).toBeInTheDocument();
    expect(screen.getByText(/2 de 3 personas siguen sin calificar/)).toBeInTheDocument();
  });

  it("el botón de guardar solo se activa si la nota cambió y es válida", async () => {
    const usuario = userEvent.setup();
    const fila = await (montarLista(), filaDe("Beto Bernal"));
    const campo = within(fila).getByLabelText("Nota de Beto Bernal");

    expect(within(fila).getByRole("button", { name: "Guardar" })).toBeDisabled();

    await usuario.type(campo, "9");
    expect(within(fila).getByRole("button", { name: "Guardar" })).toBeDisabled();

    await usuario.clear(campo);
    await usuario.type(campo, "4.5");
    expect(within(fila).getByRole("button", { name: "Guardar" })).toBeEnabled();
  });

  it("guarda una fila sin tocar las demás", async () => {
    // Calificar cuarenta personas se hace a ratos. Un «guardar todo» obligaría a terminarlo de
    // una sentada o perderlo.
    const enviados: string[] = [];
    server.use(
      http.put(
        `${API_URL}/api/v1/professors/me/offerings/:offeringId/grades/:studentId`,
        ({ params }) => {
          enviados.push(String(params.studentId));
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );

    const usuario = userEvent.setup();
    const fila = await (montarLista(), filaDe("Beto Bernal"));

    await usuario.type(within(fila).getByLabelText("Nota de Beto Bernal"), "3.5");
    await usuario.click(within(fila).getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Nota guardada.")).toBeInTheDocument();
    expect(enviados).toEqual(["e2"]);
  });

  it("explica que la persona canceló en vez de mostrar un fallo genérico", async () => {
    // Pasa de verdad: alguien cancela después de que el docente abra la lista.
    const usuario = userEvent.setup();
    const fila = await (montarLista(), filaDe("Zoe Zapata"));

    await usuario.type(within(fila).getByLabelText("Nota de Zoe Zapata"), "3.0");
    await usuario.click(within(fila).getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText("Esa persona canceló la materia")).toBeInTheDocument();
  });

  it("explica que el grupo es de otro docente sin decir que no existe", async () => {
    // Son dos problemas distintos: uno se arregla revisando la URL y el otro hablando con
    // Registro Académico.
    montarLista("g2");

    expect(await screen.findByText("Ese grupo no es tuyo")).toBeInTheDocument();
  });
});
