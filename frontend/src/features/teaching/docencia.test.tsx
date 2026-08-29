/**
 * Pruebas del acceso y la pantalla del docente (iteración 9.1).
 *
 * Lo que se comprueba es sobre todo lo que el rol nuevo **cambia para los demás**:
 *
 * - Que la navegación no le ofrezca al docente los enlaces del estudiante. Tiene sesión y no
 *   tiene plan, ni materias propias: esos enlaces llevarían a pantallas que responden
 *   `STUDENT_PROFILE_NOT_FOUND`, y el error parecería del sistema y no del menú.
 * - Que `/docencia` explique la negativa en vez de dejar la pantalla llenándose de 403.
 * - Que los dos vacíos —sin período y sin carga— se digan distinto. Se ven igual y significan
 *   cosas diferentes.
 */

import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, USUARIO, parDeTokens } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

function montar(rol: "PROFESSOR" | "STUDENT" | "ADMIN", ruta: string) {
  server.use(
    http.post(`${API_URL}/api/v1/auth/refresh`, () =>
      HttpResponse.json({ ...parDeTokens("renovado"), user: { ...USUARIO, role: rol } }),
    ),
  );
  guardarRefreshToken("refresh-de-prueba");

  return renderConProveedores(<AppRoutes />, { ruta });
}

describe("acceso del docente", () => {
  it("le ofrece sus grupos y no los enlaces del estudiante", async () => {
    // Un docente tiene sesión y no tiene plan ni materias propias. Ofrecérselos le llevaría a
    // pantallas que fallan con un error que parece del sistema.
    montar("PROFESSOR", "/docencia");

    // El `<nav>` existe ANTES de que llegue el rol —se pinta con «Inicio» mientras la sesión se
    // restaura—, así que el enlace se ESPERA en vez de consultarse de golpe. Consultarlo de
    // forma síncrona pasa en una máquina descargada y falla en cuanto la suite corre varios
    // archivos a la vez, con un mensaje que no dice que el problema era la espera.
    const navegacion = await screen.findByRole("navigation");
    expect(
      await within(navegacion).findByRole("link", { name: "Mis grupos" }),
    ).toBeInTheDocument();
    expect(within(navegacion).queryByRole("link", { name: "Mi plan" })).not.toBeInTheDocument();
    expect(
      within(navegacion).queryByRole("link", { name: "Mis materias" }),
    ).not.toBeInTheDocument();
  });

  it("no le ofrece «Mis grupos» a un estudiante", async () => {
    montar("STUDENT", "/");

    const navegacion = await screen.findByRole("navigation");
    expect(await within(navegacion).findByRole("link", { name: "Mi plan" })).toBeInTheDocument();
    expect(within(navegacion).queryByRole("link", { name: "Mis grupos" })).not.toBeInTheDocument();
  });

  it("explica la negativa a quien no es docente, en vez de dejar la pantalla vacía", async () => {
    // Sin esto, un estudiante que escriba /docencia vería una pantalla llenándose de 403 sin
    // entender por qué.
    montar("STUDENT", "/docencia");

    expect(await screen.findByText("Esta sección es para docentes")).toBeInTheDocument();
  });

  it("un administrador tampoco entra", async () => {
    // Va contra el reflejo de que «admin puede todo», y es a propósito: quien conoce la nota es
    // quien dictó la clase.
    montar("ADMIN", "/docencia");

    expect(await screen.findByText("Esta sección es para docentes")).toBeInTheDocument();
  });
});

describe("mis grupos", () => {
  it("muestra cuántos estudiantes hay, no cuántos cupos quedan", async () => {
    // Al docente no le sirve saber cuántas plazas quedan: no va a matricular a nadie. Le sirve
    // saber a cuánta gente tiene enfrente.
    montar("PROFESSOR", "/docencia");

    // Dentro de su tarjeta: «Cálculo I» está contenido en «Cálculo II», y buscarlo suelto
    // encuentra las dos.
    const tarjeta = (await screen.findByText("MAT101")).closest("li") as HTMLElement;
    expect(within(tarjeta).getByText(/Cálculo I$/)).toBeInTheDocument();
    expect(within(tarjeta).getByText("10")).toBeInTheDocument();
    expect(within(tarjeta).getByText(/estudiantes inscritos/)).toBeInTheDocument();
    expect(within(tarjeta).getByText(/de 40 cupos/)).toBeInTheDocument();
  });

  it("concuerda el singular cuando hay un solo inscrito", async () => {
    montar("PROFESSOR", "/docencia");

    expect(await screen.findByText(/estudiante inscrito$/)).toBeInTheDocument();
  });

  it("distingue no tener carga de no haber período abierto", async () => {
    // Los dos vacíos se ven igual y mandan a sitios distintos: uno a esperar al semestre, otro
    // a preguntar por la asignación.
    server.use(
      http.get(`${API_URL}/api/v1/professors/me/offerings`, () =>
        HttpResponse.json({
          period_code: null,
          academic_period: null,
          items: [],
          total: 0,
        }),
      ),
    );

    montar("PROFESSOR", "/docencia");

    expect(await screen.findByText("No hay un período de matrícula abierto")).toBeInTheDocument();
  });

  it("dice que no tiene asignación cuando sí hay período", async () => {
    server.use(
      http.get(`${API_URL}/api/v1/professors/me/offerings`, () =>
        HttpResponse.json({
          period_code: "2025-2-V1",
          academic_period: "2025-2",
          items: [],
          total: 0,
        }),
      ),
    );

    montar("PROFESSOR", "/docencia");

    expect(
      await screen.findByText("No tienes grupos asignados este período"),
    ).toBeInTheDocument();
  });
});
