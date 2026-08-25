/**
 * Pruebas del flujo de inscripción.
 *
 * El grueso de estos tests son los CONFLICTOS, no el camino feliz. En una matrícula con miles
 * de personas compitiendo, los `409` son el resultado más frecuente después del éxito, y lo que
 * la pantalla diga en ese momento determina si el estudiante encuentra otro grupo o abandona.
 */

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, respuestaDeError, sembrarInscripcion } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

function montarConSesion(ruta: string) {
  guardarRefreshToken("refresh-persistido");
  return renderConProveedores(<AppRoutes />, { ruta });
}

/** Devuelve la fila del grupo indicado, para no confundirla con las de los otros grupos. */
function filaDelGrupo(numero: string) {
  const fila = screen.getByText(`Grupo ${numero}`).closest("li");
  expect(fila).not.toBeNull();
  return within(fila!);
}

describe("inscribir un grupo", () => {
  it("confirma la inscripción y la refleja en Mis materias", async () => {
    const usuario = userEvent.setup();
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 01");

    await usuario.click(screen.getByRole("button", { name: "Inscribir grupo 01" }));

    expect(await screen.findByText("Inscripción confirmada")).toBeInTheDocument();

    // El recorrido completo: lo inscrito aparece donde la persona va a buscarlo.
    await usuario.click(screen.getByRole("link", { name: "Mis materias" }));
    expect(await screen.findByText("Cálculo I")).toBeInTheDocument();
  });

  it("bloquea el botón mientras la petición viaja", async () => {
    // Sin esto, dos pulsaciones rápidas serían dos intentos y el segundo recibiría un
    // ALREADY_ENROLLED desconcertante.
    const usuario = userEvent.setup();
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 01");

    const boton = screen.getByRole("button", { name: "Inscribir grupo 01" });
    await usuario.click(boton);

    await waitFor(() => {
      expect(screen.getByText("Inscripción confirmada")).toBeInTheDocument();
    });
  });

  it("no ofrece inscribir un grupo que ya está lleno", async () => {
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 03");

    const grupo03 = filaDelGrupo("03");
    expect(grupo03.getByRole("button", { name: "Inscribir grupo 03" })).toBeDisabled();
    // El motivo se dice en voz alta: un botón gris sin explicación deja buscando qué se hizo mal.
    expect(grupo03.getByText("Este grupo no tiene cupos disponibles.")).toBeInTheDocument();
  });

  it("dice que ya está inscrito en vez de ofrecer inscribir otra vez", async () => {
    sembrarInscripcion("g1");

    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 01");

    expect(await screen.findByText("Ya estás inscrito en este grupo")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Inscribir grupo 01" }),
    ).not.toBeInTheDocument();
  });
});

describe("conflictos al inscribir", () => {
  it("explica que alguien tomó el último cupo, no un «error 409»", async () => {
    server.use(
      http.post(`${API_URL}/api/v1/enrollments`, () =>
        respuestaDeError(409, "COURSE_CAPACITY_EXCEEDED", "El grupo no tiene cupos disponibles", {
          capacity: 40,
          enrolled: 40,
        }),
      ),
    );

    const usuario = userEvent.setup();
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 01");

    await usuario.click(screen.getByRole("button", { name: "Inscribir grupo 01" }));

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("El grupo se llenó");
    // La segunda mitad del mensaje es la que desbloquea a la persona: qué hacer ahora.
    expect(aviso).toHaveTextContent(/elige otro grupo/i);
  });

  it("dice con qué día y hora choca el horario", async () => {
    // `API.md` promete `day_of_week` y `start_time` en los details justo para esto: «choca el
    // martes a las 10:00» permite encontrar el conflicto; «choca con otra materia», no.
    server.use(
      http.post(`${API_URL}/api/v1/enrollments`, () =>
        respuestaDeError(409, "SCHEDULE_CONFLICT", "Choca con otra materia", {
          conflicting_offering_id: "g9",
          day_of_week: 2,
          start_time: "10:00:00",
        }),
      ),
    );

    const usuario = userEvent.setup();
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 01");

    await usuario.click(screen.getByRole("button", { name: "Inscribir grupo 01" }));

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("El horario choca con otra materia");
    expect(aviso).toHaveTextContent("martes a las 10:00");
  });

  it("enumera los prerrequisitos que faltan", async () => {
    server.use(
      http.post(`${API_URL}/api/v1/enrollments`, () =>
        respuestaDeError(409, "PREREQUISITES_NOT_MET", "Faltan prerrequisitos", {
          missing_prerequisites: ["MAT101", "FIS101"],
        }),
      ),
    );

    const usuario = userEvent.setup();
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 01");

    await usuario.click(screen.getByRole("button", { name: "Inscribir grupo 01" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("MAT101, FIS101");
  });

  it("dice qué materias hay que inscribir a la vez cuando falta un correquisito", async () => {
    // El correquisito se distingue del prerrequisito precisamente porque SÍ tiene arreglo
    // ahora mismo: el mensaje tiene que decir cuáles inscribir, no solo que falta algo.
    server.use(
      http.post(`${API_URL}/api/v1/enrollments`, () =>
        respuestaDeError(409, "COREQUISITES_NOT_MET", "Faltan correquisitos", {
          missing_corequisites: ["TAL101"],
        }),
      ),
    );

    const usuario = userEvent.setup();
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 01");

    await usuario.click(screen.getByRole("button", { name: "Inscribir grupo 01" }));

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("Falta inscribir una materia que va junto a esta");
    expect(aviso).toHaveTextContent("TAL101");
  });

  it("explica que la materia no es del programa del estudiante", async () => {
    server.use(
      http.post(`${API_URL}/api/v1/enrollments`, () =>
        respuestaDeError(403, "COURSE_NOT_IN_PROGRAM", "No pertenece a tu programa"),
      ),
    );

    const usuario = userEvent.setup();
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 01");

    await usuario.click(screen.getByRole("button", { name: "Inscribir grupo 01" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Esta materia no es de tu programa",
    );
  });

  it("avisa de que la inscripción pudo registrarse cuando falla la red", async () => {
    // Reintentar a ciegas y acabar con dos inscripciones sería peor que revisar antes.
    server.use(http.post(`${API_URL}/api/v1/enrollments`, () => Response.error()));

    const usuario = userEvent.setup();
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 01");

    await usuario.click(screen.getByRole("button", { name: "Inscribir grupo 01" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Mis materias/);
  });
});

describe("mis materias", () => {
  it("muestra lo inscrito con sus créditos sumados", async () => {
    sembrarInscripcion("g1");
    montarConSesion("/mis-materias");

    expect(await screen.findByText("Cálculo I")).toBeInTheDocument();
    expect(screen.getByText(/1 materia inscrita · 4 créditos/)).toBeInTheDocument();
  });

  it("invita al catálogo cuando no hay nada inscrito", async () => {
    // Una lista vacía sin explicación se lee como un fallo de carga.
    montarConSesion("/mis-materias");

    expect(
      await screen.findByText("Todavía no has inscrito ninguna materia"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ir al catálogo" })).toBeInTheDocument();
  });

  it("pide confirmación antes de cancelar, nombrando la consecuencia", async () => {
    const usuario = userEvent.setup();
    sembrarInscripcion("g1");
    montarConSesion("/mis-materias");
    await screen.findByText("Cálculo I");

    await usuario.click(screen.getByRole("button", { name: /Cancelar MAT101 grupo 01/ }));

    // Durante la matrícula el cupo liberado puede desaparecer en segundos: decirlo es más útil
    // que un «¿estás seguro?» genérico.
    expect(screen.getByText(/liberas tu cupo/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Conservar" })).toBeInTheDocument();
  });

  it("cancela y deja de mostrar la materia", async () => {
    const usuario = userEvent.setup();
    sembrarInscripcion("g1");
    montarConSesion("/mis-materias");
    await screen.findByText("Cálculo I");

    await usuario.click(screen.getByRole("button", { name: /Cancelar MAT101 grupo 01/ }));
    await usuario.click(screen.getByRole("button", { name: "Sí, cancelar" }));

    expect(
      await screen.findByText("Todavía no has inscrito ninguna materia"),
    ).toBeInTheDocument();
  });

  it("permite echarse atrás sin cancelar", async () => {
    const usuario = userEvent.setup();
    sembrarInscripcion("g1");
    montarConSesion("/mis-materias");
    await screen.findByText("Cálculo I");

    await usuario.click(screen.getByRole("button", { name: /Cancelar MAT101 grupo 01/ }));
    await usuario.click(screen.getByRole("button", { name: "Conservar" }));

    expect(screen.getByText("Cálculo I")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sí, cancelar" })).not.toBeInTheDocument();
  });
});

describe("horario", () => {
  it("organiza las clases por día", async () => {
    sembrarInscripcion("g1");
    montarConSesion("/horario");

    // La tabla se anuncia con su descripción, que es lo que sitúa a quien no la ve.
    expect(
      await screen.findByRole("table", {
        name: /Horario semanal de clases, organizado por día de la semana/,
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("MAT101").length).toBeGreaterThan(0);
  });

  it("explica el horario vacío en vez de mostrar una rejilla en blanco", async () => {
    montarConSesion("/horario");

    expect(await screen.findByText("Tu horario está vacío")).toBeInTheDocument();
  });
});
