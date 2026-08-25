/**
 * Pruebas del catálogo.
 *
 * Los tests entran con sesión —guardando un refresh token antes de montar— porque el catálogo
 * es una ruta protegida. Es el mismo recorrido que hace una persona: recarga la página con la
 * sesión guardada y aterriza en el catálogo.
 */

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, respuestaDeError } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

/** Monta la aplicación con sesión activa en la ruta indicada. */
function montarConSesion(ruta: string) {
  guardarRefreshToken("refresh-persistido");
  return renderConProveedores(<AppRoutes />, { ruta });
}

describe("listado del catálogo", () => {
  it("muestra por defecto solo las materias de la carrera del estudiante", async () => {
    // Es el arreglo de fondo de la iteración 6.1: antes se listaba el catálogo entero, así
    // que alguien de Derecho veía Programación II y solo al pulsar «Inscribir» recibía un 403.
    montarConSesion("/catalogo");

    expect(await screen.findByText("Cálculo I")).toBeInTheDocument();
    expect(screen.getByText("Cálculo II")).toBeInTheDocument();
    // Física no está en el plan de estudios de prueba.
    expect(screen.queryByText("Física")).not.toBeInTheDocument();
  });

  it("filtra por el texto buscado dentro de la carrera", async () => {
    const usuario = userEvent.setup();
    montarConSesion("/catalogo");
    await screen.findByText("Cálculo I");

    await usuario.type(screen.getByLabelText("Buscar materia"), "Cálculo II");

    // La búsqueda espera antes de lanzarse: sin ese retardo, cada tecla sería una petición.
    await waitFor(
      () => {
        expect(screen.queryByText("Cálculo I")).not.toBeInTheDocument();
      },
      { timeout: 3000 },
    );
    expect(screen.getByText("Cálculo II")).toBeInTheDocument();
  });

  it("explica el resultado vacío y ofrece limpiar los filtros", async () => {
    // Una lista vacía sin explicación se lee como un fallo de carga.
    const usuario = userEvent.setup();
    montarConSesion("/catalogo");
    await screen.findByText("Cálculo I");

    await usuario.type(screen.getByLabelText("Buscar materia"), "materia-que-no-existe");

    expect(
      await screen.findByText("Ninguna materia coincide con la búsqueda", undefined, {
        timeout: 3000,
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Limpiar filtros" }).length).toBeGreaterThan(0);
  });

  it("aplica el filtro del semestre del estudiante", async () => {
    const usuario = userEvent.setup();
    montarConSesion("/catalogo");
    await screen.findByText("Cálculo I");

    // El perfil de prueba está en sexto semestre; solo Cálculo I está sugerida ahí.
    await usuario.click(screen.getByRole("button", { name: "Semestre 6" }));

    await waitFor(() => {
      expect(screen.queryByText("Cálculo II")).not.toBeInTheDocument();
    });
    // `aria-pressed` es lo que comunica a un lector de pantalla que el filtro está aplicado.
    expect(screen.getByRole("button", { name: "Semestre 6" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("arranca con los filtros que vienen en la URL", async () => {
    // Es lo que hace que un enlace compartido lleve a la misma búsqueda.
    montarConSesion("/catalogo?q=C%C3%A1lculo%20II");

    expect(await screen.findByText("Cálculo II")).toBeInTheDocument();
    expect(screen.queryByText("Cálculo I")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Buscar materia")).toHaveValue("Cálculo II");
  });

  it("permite ver todo el catálogo como decisión explícita", async () => {
    // Ver el catálogo completo sigue siendo posible; lo que cambia es que no es el estado en
    // el que la persona se encuentra sin saber cómo llegó.
    const usuario = userEvent.setup();
    montarConSesion("/catalogo");
    await screen.findByText("Cálculo I");

    await usuario.click(screen.getByRole("button", { name: "Todo el catálogo" }));

    expect(await screen.findByText("Física")).toBeInTheDocument();
  });

  it("marca las materias que no pertenecen al plan de estudios", async () => {
    // Atenuarlas sin explicar sería peor que no atenuarlas: se leería como un fallo de carga.
    montarConSesion("/catalogo?alcance=todo");

    expect(await screen.findByText("Física")).toBeInTheDocument();
    expect(screen.getByText("No pertenece a tu plan de estudios")).toBeInTheDocument();
  });

  it("el alcance viaja en la URL y sobrevive a recargar", async () => {
    montarConSesion("/catalogo?alcance=todo");

    expect(await screen.findByText("Física")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Todo el catálogo" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("avisa cuando el catálogo no se puede cargar", async () => {
    server.use(http.get(`${API_URL}/api/v1/courses`, () => HttpResponse.error()));

    montarConSesion("/catalogo");

    expect(await screen.findByRole("alert")).toHaveTextContent(/No se pudo cargar el catálogo/);
  });
});

describe("estado de la ventana de matrícula", () => {
  it("muestra cuánto queda cuando está abierta", async () => {
    montarConSesion("/catalogo");

    expect(await screen.findByText(/Matrícula abierta/)).toBeInTheDocument();
    // Dos días, redondeado a la unidad mayor: un contador al segundo genera urgencia sin
    // aportar información.
    expect(screen.getByText(/Cierra en 2 días/)).toBeInTheDocument();
  });

  it("explica que no hay matrícula abierta sin presentarlo como un error", async () => {
    // Es el estado normal durante la mayor parte del semestre, no una avería.
    server.use(
      http.get(`${API_URL}/api/v1/enrollment-periods/current`, () =>
        respuestaDeError(404, "NO_ACTIVE_PERIOD", "No hay un período de matrícula activo"),
      ),
    );

    montarConSesion("/catalogo");

    expect(await screen.findByText("No hay matrícula abierta")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("distingue una ventana activada que todavía no admite inscripciones", async () => {
    server.use(
      http.get(`${API_URL}/api/v1/enrollment-periods/current`, () =>
        HttpResponse.json({
          id: "p1",
          code: "2026-1-V1",
          academic_period: "2026-1",
          name: "Matrícula 2026-1",
          starts_at: "2026-01-20T08:00:00Z",
          ends_at: "2026-01-22T18:00:00Z",
          is_active: true,
          is_open: false,
          time_remaining_seconds: 0,
        }),
      ),
    );

    montarConSesion("/catalogo");

    expect(
      await screen.findByText(/La ventana de matrícula no está abierta en este momento/),
    ).toBeInTheDocument();
  });
});

describe("detalle de una materia", () => {
  it("muestra los grupos con sus cupos y su horario", async () => {
    montarConSesion("/catalogo/c1");

    expect(await screen.findByRole("heading", { name: "Cálculo I", level: 1 })).toBeInTheDocument();

    const grupo01 = screen.getByText("Grupo 01").closest("li");
    expect(grupo01).not.toBeNull();
    expect(within(grupo01!).getByText("30 de 40 cupos")).toBeInTheDocument();
    expect(within(grupo01!).getByText("Ana Pérez")).toBeInTheDocument();
    expect(within(grupo01!).getByText("Lun 08:00–10:00")).toBeInTheDocument();
  });

  it("avisa de los grupos que están a punto de llenarse", async () => {
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 02");

    // Con dos plazas y miles de personas conectadas, el grupo puede llenarse mientras se
    // decide: decirlo es información útil.
    expect(screen.getByText("Quedan 2 cupos")).toBeInTheDocument();
  });

  it("marca como sin cupos el grupo lleno", async () => {
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 03");

    expect(screen.getByText("Sin cupos")).toBeInTheDocument();
  });

  it("indica cuándo un grupo no tiene docente asignado", async () => {
    // Un hueco vacío se leería como un fallo de carga.
    montarConSesion("/catalogo/c1");
    await screen.findByText("Grupo 02");

    expect(screen.getByText("Docente por asignar")).toBeInTheDocument();
  });

  it("enlaza los prerrequisitos con su propia ficha", async () => {
    montarConSesion("/catalogo/c2");

    expect(await screen.findByRole("heading", { name: "Cálculo II", level: 1 })).toBeInTheDocument();
    const enlace = screen.getByRole("link", { name: /MAT101/ });
    expect(enlace).toHaveAttribute("href", "/catalogo/c1");
  });

  it("bloquea la inscripción de una materia ajena al plan de estudios", async () => {
    // Se llega aquí por un enlace directo o desde «todo el catálogo». Ofrecer el botón sería
    // empujar hacia un 403 que ya se sabe que va a ocurrir.
    montarConSesion("/catalogo/c3");

    expect(await screen.findByText("Esta materia no es de tu carrera")).toBeInTheDocument();
  });

  it("no bloquea las materias que sí son del plan", async () => {
    // La comprobación no debe disparar un falso positivo mientras el plan todavía carga.
    montarConSesion("/catalogo/c1");

    await screen.findByText("Grupo 01");
    expect(screen.queryByText("Esta materia no es de tu carrera")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inscribir grupo 01" })).toBeEnabled();
  });

  it("explica que una materia no existe en vez de mostrar una pantalla rota", async () => {
    montarConSesion("/catalogo/no-existe");

    expect(await screen.findByText("Esta materia no existe")).toBeInTheDocument();
  });

  it("dice que la materia no tiene grupos abiertos", async () => {
    montarConSesion("/catalogo/c3");

    expect(await screen.findByText("Esta materia no tiene grupos abiertos")).toBeInTheDocument();
  });
});
