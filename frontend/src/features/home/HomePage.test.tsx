/**
 * Pruebas de la pantalla de inicio (iteración 6.4).
 *
 * Comprueban las dos mitades de la limpieza: que el andamiaje de desarrollo ya no está delante
 * del estudiante, y que lo que ocupó su sitio lleva de verdad a alguna parte. Lo primero es
 * fácil de revertir sin querer —basta con que alguien vuelva a montar el componente «para
 * depurar»— y por eso se afirma en un test en vez de confiarlo al comentario del código.
 */

import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, USUARIO, parDeTokens } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

function montarConSesion() {
  guardarRefreshToken("refresh-de-prueba");
  return renderConProveedores(<AppRoutes />, { ruta: "/" });
}

/** Monta la pantalla de inicio con una sesión del rol indicado. */
function montarComo(rol: "STUDENT" | "PROFESSOR" | "ADMIN") {
  server.use(
    http.post(`${API_URL}/api/v1/auth/refresh`, () =>
      HttpResponse.json({ ...parDeTokens("renovado"), user: { ...USUARIO, role: rol } }),
    ),
  );
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

  it("lleva a las cinco pantallas del estudiante", async () => {
    // Una pantalla de inicio que no lleva a ninguna parte obliga a buscar en la barra de
    // navegación lo que debería estar delante.
    montarConSesion();
    const accesos = await screen.findByRole("region", { name: "Qué quieres hacer" });

    const destinos = within(accesos)
      .getAllByRole("link")
      .map((enlace) => enlace.getAttribute("href"));

    // El orden es el MISMO de la barra de navegación, a propósito: dos ordenaciones
    // distintas para los mismos destinos obligan a releer cada vez.
    expect(destinos).toEqual([
      "/plan",
      "/catalogo",
      "/mis-materias",
      "/horario",
      "/expediente",
    ]);
  });

  it("no le ofrece al admin las pantallas del estudiante", async () => {
    // Es el hallazgo #3 de la QA manual. La barra de navegación filtraba por rol desde la Fase
    // 9; esta pantalla se quedó atrás, así que un administrador veía los cinco accesos del
    // estudiante y al pulsar cualquiera recibía `STUDENT_PROFILE_NOT_FOUND` — un error que
    // parece del sistema y es del menú.
    montarComo("ADMIN");
    const accesos = await screen.findByRole("region", { name: "Qué quieres hacer" });

    const destinos = within(accesos)
      .getAllByRole("link")
      .map((enlace) => enlace.getAttribute("href"));

    expect(destinos).toEqual(["/admin"]);
  });

  it("le ofrece al docente sus grupos y nada del estudiante", async () => {
    montarComo("PROFESSOR");
    const accesos = await screen.findByRole("region", { name: "Qué quieres hacer" });

    const destinos = within(accesos)
      .getAllByRole("link")
      .map((enlace) => enlace.getAttribute("href"));

    expect(destinos).toEqual(["/docencia"]);
  });

  it("le habla a cada rol de su trabajo, no del de otro", async () => {
    // «Inscribe tus materias, revisa tu horario y descarga tu comprobante» era el único
    // subtítulo, y a quien administra le describe un trabajo que no es el suyo.
    montarComo("ADMIN");

    expect(await screen.findByText(/Gestiona las ventanas de matrícula/)).toBeInTheDocument();
    expect(screen.queryByText(/Inscribe tus materias/)).not.toBeInTheDocument();
  });

  it("no le pide el perfil académico a quien no es estudiante", async () => {
    // `GET /students/me` responde 404 a un administrador: no tiene perfil que devolver. Sin la
    // guarda, cada carga gastaba una petición para recibir un error previsible.
    let consultas = 0;
    server.use(
      http.get(`${API_URL}/api/v1/students/me`, () => {
        consultas += 1;
        return HttpResponse.json({ error: { code: "STUDENT_PROFILE_NOT_FOUND" } }, { status: 404 });
      }),
    );
    montarComo("ADMIN");
    await screen.findByRole("region", { name: "Qué quieres hacer" });

    expect(consultas).toBe(0);
    // Y sin perfil no se pinta la tarjeta de datos académicos, que es de estudiante.
    expect(screen.queryByText("Tus datos académicos")).not.toBeInTheDocument();
  });
});
