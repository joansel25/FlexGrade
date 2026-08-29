/**
 * Pruebas de la pantalla del expediente académico (iteración 9.4).
 *
 * Lo que se comprueba aquí no es el cálculo —los promedios ponderados y el `status` derivado de
 * la nota viven en el backend, que es donde se decide—, sino que la pantalla **respeta** lo que
 * el servidor manda. Tres promesas del expediente se pueden romper en el cliente sin que ningún
 * test del backend se entere: esconder lo perdido, colapsar la materia repetida en una sola
 * fila, y rehacer un promedio con otra fórmula o en coma flotante.
 */

import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, USUARIO, parDeTokens, respuestaDeError } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

function montarConSesion(ruta = "/expediente") {
  guardarRefreshToken("refresh-de-prueba");
  return renderConProveedores(<AppRoutes />, { ruta });
}

/** Monta la aplicación con una sesión de un rol concreto. */
function montarComo(rol: "STUDENT" | "PROFESSOR", ruta: string) {
  server.use(
    http.post(`${API_URL}/api/v1/auth/refresh`, () =>
      HttpResponse.json({ ...parDeTokens("renovado"), user: { ...USUARIO, role: rol } }),
    ),
  );
  guardarRefreshToken("refresh-de-prueba");

  return renderConProveedores(<AppRoutes />, { ruta });
}

/** Sustituye el expediente por uno a medida, para provocar un estado concreto. */
function servirExpediente(cuerpo: Record<string, unknown>) {
  server.use(
    http.get(`${API_URL}/api/v1/students/me/history`, () => HttpResponse.json(cuerpo)),
  );
}

/** Devuelve la tabla de un semestre, por el título de su sección. */
async function tablaDelSemestre(periodo: string) {
  const seccion = await screen.findByRole("region", { name: periodo });
  return within(seccion).getByRole("table");
}

describe("expediente académico", () => {
  it("agrupa lo cursado por semestre, del más reciente al más antiguo", async () => {
    montarConSesion();

    const titulos = await screen.findAllByRole("heading", { level: 2 });

    expect(titulos.map((t) => t.textContent)).toEqual(["2024-2", "2024-1"]);
  });

  it("muestra las materias perdidas junto a las aprobadas", async () => {
    // Un expediente que oculta lo reprobado no es un expediente, y además dejaría de cuadrar
    // con el certificado oficial que la institución emite.
    montarConSesion();

    expect(await screen.findByText("Perdida")).toBeInTheDocument();
    expect(screen.getAllByText("Aprobada")).toHaveLength(2);
  });

  it("repite la materia cursada dos veces, una en cada semestre", async () => {
    // Colapsarla en una fila «la última vale» borraría el intento perdido, que es un hecho del
    // historial y lo que explica por qué hay créditos cursados que no se aprobaron.
    montarConSesion();

    const segundo = await tablaDelSemestre("2024-2");
    const primero = await tablaDelSemestre("2024-1");

    expect(within(segundo).getByText("MAT101")).toBeInTheDocument();
    expect(within(primero).getByText("MAT101")).toBeInTheDocument();
    // Y con notas distintas: son dos hechos, no uno repetido.
    expect(within(segundo).getByText("3.80")).toBeInTheDocument();
    expect(within(primero).getByText("2.10")).toBeInTheDocument();
  });

  it("pinta el promedio del servidor y no lo recalcula", async () => {
    // El del semestre 2024-1 es ponderado: (2.10×4 + 4.00×3) / 7 = 2.91. Una media simple daría
    // 3.05, así que ver 2.91 demuestra que la cifra viene del servidor.
    montarConSesion();

    const seccion = await screen.findByRole("region", { name: "2024-1" });

    expect(within(seccion).getByText("2.91")).toBeInTheDocument();
    expect(within(seccion).queryByText("3.05")).not.toBeInTheDocument();
  });

  it("conserva los dos decimales exactos que manda el servidor", async () => {
    // `4.00` convertido a número y pintado se vería como `4`. La nota de un expediente se
    // escribe con dos decimales, y perderlos hace que no coincida con el documento oficial.
    // El expediente es mínimo a propósito: con una sola cifra `4.00` en pantalla, el test no
    // puede pasar por casualidad porque la encontró en otra fila.
    servirExpediente({
      student_code: "1234567",
      full_name: "Joan Sebastián Cárdenas",
      periods: [
        {
          academic_period: "2024-1",
          entries: [
            {
              course_id: "c1",
              code: "MAT101",
              name: "Cálculo I",
              credits: 4,
              final_grade: "3.50",
              status: "APPROVED",
            },
          ],
          credits_attempted: 4,
          credits_approved: 4,
          average: "3.50",
        },
      ],
      total_credits_approved: 4,
      cumulative_average: "4.00",
    });
    montarConSesion();

    expect(await screen.findByText("4.00")).toBeInTheDocument();
  });

  it("anuncia el acumulado y los créditos aprobados en la cabecera", async () => {
    // «en total» distingue esta cifra de la de cada semestre: sin ella, «7 créditos aprobados»
    // en la cabecera y «3 de 7 créditos aprobados» en una sección se leen como lo mismo.
    montarConSesion();

    expect(await screen.findByText(/7 créditos aprobados en total/)).toBeInTheDocument();
    expect(screen.getByText("3.30")).toBeInTheDocument();
  });

  it("trata el expediente vacío como un estado normal y no como un error", async () => {
    // Es lo que ve quien acaba de ingresar. Presentarlo como fallo le haría buscar un problema
    // que no existe, o escribir a Registro Académico por algo correcto.
    servirExpediente({
      student_code: "1234567",
      full_name: "Joan Sebastián Cárdenas",
      periods: [],
      total_credits_approved: 0,
      cumulative_average: "0.00",
    });
    montarConSesion();

    expect(await screen.findByText(/Todavía no tienes semestres cerrados/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // Y sin anunciar un «promedio acumulado 0.00», que se leería como una nota y no como un
    // vacío.
    expect(screen.queryByText(/promedio acumulado/)).not.toBeInTheDocument();
  });

  it("enlaza el expediente solo desde la navegación del estudiante", async () => {
    // Un docente tiene sesión y no tiene expediente: el enlace le llevaría a una pantalla que
    // responde `STUDENT_PROFILE_NOT_FOUND`, y el error parecería del sistema y no del menú.
    montarComo("PROFESSOR", "/");

    const navegacion = await screen.findByRole("navigation");
    // Se espera PRIMERO el enlace propio del docente. El `<nav>` existe desde el principio, con
    // «Inicio» dentro, mientras la sesión se restaura: comprobar la ausencia sin ese anclaje
    // daría por bueno el instante en que todavía no hay ningún enlace de rol, y el test pasaría
    // aunque la regla se rompiera.
    await within(navegacion).findByRole("link", { name: "Mis grupos" });

    expect(within(navegacion).queryByRole("link", { name: "Expediente" })).not.toBeInTheDocument();
  });

  it("le ofrece el expediente al estudiante en la navegación", async () => {
    montarComo("STUDENT", "/");

    const navegacion = await screen.findByRole("navigation");

    expect(
      await within(navegacion).findByRole("link", { name: "Expediente" }),
    ).toBeInTheDocument();
  });

  it("avisa cuando el expediente no se pudo cargar", async () => {
    server.use(
      http.get(`${API_URL}/api/v1/students/me/history`, () =>
        respuestaDeError(404, "STUDENT_PROFILE_NOT_FOUND", "La cuenta no tiene perfil académico"),
      ),
    );
    montarConSesion();

    expect(await screen.findByText("No se pudo cargar tu expediente")).toBeInTheDocument();
  });
});
