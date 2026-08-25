/**
 * Pruebas de la vista del plan de estudios (iteración 6.3).
 *
 * Lo que se comprueba aquí NO es que los estados se calculen bien —eso vive en el backend, que
 * es donde se decide si una inscripción se acepta—, sino que la pantalla **respeta** lo que el
 * servidor manda. Es la otra mitad de la promesa de la iteración: de nada sirve calcular el
 * semáforo en un solo sitio si la interfaz deja pulsar lo que él marcó como bloqueado.
 */

import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, PLAN_DE_ESTUDIOS } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

function montarConSesion(ruta = "/plan") {
  guardarRefreshToken("refresh-de-prueba");
  return renderConProveedores(<AppRoutes />, { ruta });
}

/** Sustituye el plan por uno a medida, para provocar un estado concreto. */
function servirPlan(courses: unknown[], extra: Record<string, unknown> = {}) {
  server.use(
    http.get(`${API_URL}/api/v1/students/me/study-plan`, () =>
      HttpResponse.json({ ...PLAN_DE_ESTUDIOS, courses, ...extra }),
    ),
  );
}

describe("plan de estudios", () => {
  it("agrupa las materias por semestre", async () => {
    montarConSesion();

    expect(await screen.findByRole("heading", { name: "Semestre 1" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Semestre 2" })).toBeInTheDocument();
  });

  it("anuncia el estado de cada materia con palabras, no solo con color", async () => {
    // El color por sí solo no lo ve quien tiene daltonismo ni quien usa lector de pantalla.
    montarConSesion();

    expect(await screen.findByText("Aprobada")).toBeInTheDocument();
    expect(screen.getByText("Bloqueada")).toBeInTheDocument();
    expect(screen.getByText("Puedes inscribirla")).toBeInTheDocument();
  });

  it("dice por qué está bloqueada una materia", async () => {
    // «Bloqueada» a secas deja a la persona igual de atascada que antes de mirar.
    montarConSesion();

    expect(await screen.findByText(/Antes debes aprobar: MAT101/)).toBeInTheDocument();
  });

  it("solo enlaza a la ficha las materias que se pueden inscribir", async () => {
    // Ofrecer entrar a la ficha de una bloqueada lleva a un botón «Inscribir» que va a fallar:
    // exactamente el camino que cerró la 6.1.
    montarConSesion();
    await screen.findByText("Aprobada");

    expect(screen.getByRole("link", { name: /TAL101/ })).toHaveAttribute(
      "href",
      "/catalogo/c4",
    );
    expect(screen.queryByRole("link", { name: /MAT102/ })).not.toBeInTheDocument();
  });

  it("no ofrece inscribir una materia sin grupos este período", async () => {
    servirPlan([
      {
        ...PLAN_DE_ESTUDIOS.courses[0],
        status: "NOT_OFFERED",
        missing_prerequisites: [],
        missing_corequisites: [],
        corequisites: [],
      },
    ]);
    montarConSesion();

    expect(await screen.findByText("Sin grupos este período")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /MAT101/ })).not.toBeInTheDocument();
  });

  it("distingue la materia que ya está cursando", async () => {
    servirPlan([
      {
        ...PLAN_DE_ESTUDIOS.courses[0],
        status: "ENROLLED",
        missing_prerequisites: [],
        missing_corequisites: [],
        corequisites: [],
      },
    ]);
    montarConSesion();

    expect(await screen.findByText("Cursándola")).toBeInTheDocument();
  });

  it("explica cuando el correquisito es lo que bloquea", async () => {
    // Cumplir los prerrequisitos no basta si lo que hay que cursar a la vez no tiene grupos, y
    // el motivo tiene que distinguirse del otro para que la persona sepa qué esperar.
    servirPlan([
      {
        ...PLAN_DE_ESTUDIOS.courses[0],
        status: "BLOCKED",
        missing_prerequisites: [],
        missing_corequisites: ["FIS102"],
        corequisites: ["FIS102"],
      },
    ]);
    montarConSesion();

    expect(await screen.findByText(/Se cursa junto a FIS102/)).toBeInTheDocument();
  });

  it("muestra el avance en créditos, no en número de materias", async () => {
    // Un plan mezcla materias de 1 y de 4 créditos: contarlas por unidades daría un avance que
    // no corresponde con el esfuerzo real.
    montarConSesion();

    expect(await screen.findByText(/4 de 9 créditos aprobados/)).toBeInTheDocument();
    const barra = screen.getByRole("progressbar", { name: "Avance del plan de estudios" });
    expect(barra).toHaveAttribute("aria-valuenow", "44");
  });

  it("explica el plan vacío en vez de dejar la pantalla en blanco", async () => {
    servirPlan([], { total_credits: 0, approved_credits: 0 });
    montarConSesion();

    expect(
      await screen.findByText("Tu carrera todavía no tiene plan cargado"),
    ).toBeInTheDocument();
  });

  it("ofrece el plan en la navegación de quien tiene sesión", async () => {
    montarConSesion("/");

    // Se espera: la sesión se confirma renovando el token, así que los enlaces protegidos no
    // están en el primer render.
    const enlace = await screen.findByRole("link", { name: "Mi plan" });

    expect(within(screen.getByRole("navigation")).getByRole("link", { name: "Mi plan" })).toBe(
      enlace,
    );
    expect(enlace).toHaveAttribute("href", "/plan");
  });
});
