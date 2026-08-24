/**
 * Pruebas del cliente HTTP.
 *
 * Es la capa por la que pasa TODA la comunicación con el backend: si interpreta mal un error,
 * la pantalla muestra el mensaje equivocado en el momento en que el estudiante más necesita
 * entender qué pasó. Por eso se prueba contra respuestas reales simuladas con MSW, no contra
 * un doble de `fetch`.
 */

import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { api } from "@/lib/api/client";
import { ApiError, NetworkError } from "@/lib/api/errors";
import { API_URL, respuestaDeError } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";

describe("cliente de la API", () => {
  it("devuelve el cuerpo ya tipado cuando la respuesta es correcta", async () => {
    const resultado = await api.get<{ status: string }>("/health");

    expect(resultado.status).toBe("ok");
  });

  it("traduce el error del contrato a un ApiError con su código", async () => {
    server.use(
      http.post(`${API_URL}/api/v1/enrollments`, () =>
        respuestaDeError(409, "COURSE_CAPACITY_EXCEEDED", "El grupo no tiene cupos disponibles", {
          offering_id: "abc",
        }),
      ),
    );

    const error = await api
      .post("/api/v1/enrollments", { body: { course_offering_id: "abc" } })
      .catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    // El `code` es lo estable: es con lo que la interfaz decide qué hacer.
    expect(apiError.code).toBe("COURSE_CAPACITY_EXCEEDED");
    expect(apiError.is("COURSE_CAPACITY_EXCEEDED")).toBe(true);
    expect(apiError.isConflict).toBe(true);
    expect(apiError.details.offering_id).toBe("abc");
  });

  it("marca como error de sesión cualquier 401", async () => {
    server.use(
      http.get(`${API_URL}/api/v1/students/me`, () =>
        respuestaDeError(401, "INVALID_TOKEN", "Token inválido"),
      ),
    );

    const error = (await api.get("/api/v1/students/me").catch((e: unknown) => e)) as ApiError;

    expect(error.isAuthError).toBe(true);
  });

  it("construye un error legible cuando la respuesta no sigue el contrato", async () => {
    // Un 502 del balanceador devuelve HTML, no el JSON de la API. Sin este camino, la
    // interfaz recibiría `undefined` y fallaría con un mensaje que no dice nada.
    server.use(
      http.get(`${API_URL}/api/v1/courses`, () =>
        HttpResponse.text("<html>502 Bad Gateway</html>", { status: 502 }),
      ),
    );

    const error = (await api.get("/api/v1/courses").catch((e: unknown) => e)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
    expect(error.message).toContain("servidor");
  });

  it("devuelve undefined ante un 204 sin cuerpo", async () => {
    server.use(
      http.delete(`${API_URL}/api/v1/enrollments/1`, () => new HttpResponse(null, { status: 204 })),
    );

    await expect(api.delete("/api/v1/enrollments/1")).resolves.toBeUndefined();
  });

  it("envía el token como Bearer cuando se le pasa", async () => {
    let recibido: string | null = null;

    server.use(
      http.get(`${API_URL}/api/v1/students/me`, ({ request }) => {
        recibido = request.headers.get("Authorization");
        return HttpResponse.json({ id: "1" });
      }),
    );

    await api.get("/api/v1/students/me", { token: "token-de-prueba" });

    expect(recibido).toBe("Bearer token-de-prueba");
  });

  it("omite de la consulta los filtros vacíos", async () => {
    let url = "";

    server.use(
      http.get(`${API_URL}/api/v1/courses`, ({ request }) => {
        url = request.url;
        return HttpResponse.json({ items: [] });
      }),
    );

    await api.get("/api/v1/courses", {
      query: { page: 1, search: undefined, program_id: null, semester: "" },
    });

    // Un `search=undefined` en la URL haría que el backend buscara la palabra "undefined".
    expect(url).toContain("page=1");
    expect(url).not.toContain("search");
    expect(url).not.toContain("program_id");
    expect(url).not.toContain("semester");
  });

  it("convierte un fallo de red en NetworkError", async () => {
    server.use(http.get(`${API_URL}/api/v1/courses`, () => HttpResponse.error()));

    const error = await api.get("/api/v1/courses").catch((e: unknown) => e);

    // Se distingue del error de negocio a propósito: aquí el servidor no dijo nada, así que
    // la interfaz debe ofrecer reintentar en vez de explicar una regla.
    expect(error).toBeInstanceOf(NetworkError);
  });
});
