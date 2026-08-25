/**
 * Pruebas del ciclo de vida de la sesión: protección de rutas, recuperación al recargar y
 * cierre.
 *
 * Son los tres comportamientos que se rompen en silencio y solo se notan cuando ya están
 * desplegados: alguien entra a una URL protegida sin sesión, alguien recarga la página en
 * mitad de la matrícula, o alguien sale y su información sigue en la pantalla.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { guardarRefreshToken, leerRefreshToken } from "@/features/auth/tokenStorage";
import { API_URL, CREDENCIALES_VALIDAS, respuestaDeError } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

describe("protección de rutas", () => {
  it("manda al login a quien entra sin sesión a una ruta protegida", async () => {
    renderConProveedores(<AppRoutes />, { ruta: "/" });

    expect(
      await screen.findByRole("heading", { name: "Iniciar sesión", level: 1 }),
    ).toBeInTheDocument();
  });

  it("devuelve a la ruta que se pedía después de entrar", async () => {
    // Quien abre el enlace directo a una pantalla debe acabar ahí, no en el inicio.
    const usuario = userEvent.setup();
    renderConProveedores(<AppRoutes />, { ruta: "/" });

    await screen.findByRole("heading", { name: "Iniciar sesión", level: 1 });

    await usuario.type(
      screen.getByLabelText("Correo institucional"),
      CREDENCIALES_VALIDAS.email,
    );
    await usuario.type(screen.getByLabelText("Contraseña"), CREDENCIALES_VALIDAS.password);
    await usuario.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("heading", { name: /Hola, Joan/, level: 1 })).toBeInTheDocument();
  });

  it("no protege la pantalla de ruta inexistente", async () => {
    // Protegerla haría que una URL mal escrita rebotara al login, que se lee como un fallo de
    // sesión en vez de como lo que es: una dirección equivocada.
    renderConProveedores(<AppRoutes />, { ruta: "/no-existe" });

    expect(
      await screen.findByRole("heading", { name: "Esta página no existe" }),
    ).toBeInTheDocument();
  });
});

describe("recuperación de la sesión al recargar", () => {
  it("canjea el refresh token guardado y mantiene la sesión", async () => {
    // Simula exactamente lo que ocurre al recargar: el access token se perdió con la pestaña,
    // el refresh token sobrevivió en `localStorage`.
    guardarRefreshToken("refresh-persistido");

    renderConProveedores(<AppRoutes />, { ruta: "/" });

    expect(await screen.findByRole("heading", { name: /Hola, Joan/, level: 1 })).toBeInTheDocument();
  });

  it("guarda el refresh token NUEVO que devuelve la renovación", async () => {
    // La API rota el token en cada refresco: conservar el viejo cerraría la sesión sola en el
    // siguiente intento, sin motivo aparente.
    guardarRefreshToken("refresh-persistido");

    renderConProveedores(<AppRoutes />, { ruta: "/" });
    await screen.findByRole("heading", { name: /Hola, Joan/, level: 1 });

    expect(leerRefreshToken()).toBe("refresh-renovado");
  });

  it("no decide nada mientras comprueba la sesión", async () => {
    // Si decidiera durante la comprobación, mandaría al login a quien sí tiene sesión.
    guardarRefreshToken("refresh-persistido");

    renderConProveedores(<AppRoutes />, { ruta: "/" });

    expect(screen.getByRole("status")).toHaveTextContent("Verificando tu sesión…");
    expect(screen.queryByRole("heading", { name: "Iniciar sesión" })).not.toBeInTheDocument();

    await screen.findByRole("heading", { name: /Hola, Joan/, level: 1 });
  });

  it("cierra la sesión si el refresh token ya no vale", async () => {
    server.use(
      http.post(`${API_URL}/api/v1/auth/refresh`, () =>
        respuestaDeError(401, "INVALID_TOKEN", "Token inválido"),
      ),
    );
    guardarRefreshToken("refresh-caducado");

    renderConProveedores(<AppRoutes />, { ruta: "/" });

    expect(
      await screen.findByRole("heading", { name: "Iniciar sesión", level: 1 }),
    ).toBeInTheDocument();
    // El token inservible se descarta: dejarlo haría que cada carga intentara un refresco
    // condenado a fallar.
    expect(leerRefreshToken()).toBeNull();
  });
});

describe("cierre de sesión", () => {
  it("descarta los tokens y devuelve al login", async () => {
    const usuario = userEvent.setup();
    guardarRefreshToken("refresh-persistido");

    renderConProveedores(<AppRoutes />, { ruta: "/" });
    await screen.findByRole("heading", { name: /Hola, Joan/, level: 1 });

    await usuario.click(screen.getByRole("button", { name: "Salir" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Iniciar sesión", level: 1 })).toBeInTheDocument();
    });
    expect(leerRefreshToken()).toBeNull();
  });

  it("cierra la sesión aunque el servidor no responda", async () => {
    // Lo que de verdad cierra la sesión es descartar los tokens en el cliente. Dejar a alguien
    // "dentro" porque el servidor no contestó sería lo peor de los dos mundos.
    server.use(http.post(`${API_URL}/api/v1/auth/logout`, () => HttpResponse.error()));

    const usuario = userEvent.setup();
    guardarRefreshToken("refresh-persistido");

    renderConProveedores(<AppRoutes />, { ruta: "/" });
    await screen.findByRole("heading", { name: /Hola, Joan/, level: 1 });

    await usuario.click(screen.getByRole("button", { name: "Salir" }));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Iniciar sesión", level: 1 })).toBeInTheDocument();
    });
  });

  it("borra de la caché los datos de quien salió", async () => {
    const usuario = userEvent.setup();
    guardarRefreshToken("refresh-persistido");

    const { queryClient } = renderConProveedores(<AppRoutes />, { ruta: "/" });
    await screen.findByRole("heading", { name: /Hola, Joan/, level: 1 });
    expect(queryClient.getQueryData(["auth", "perfil"])).toBeDefined();

    await usuario.click(screen.getByRole("button", { name: "Salir" }));

    // Sin esto, la siguiente persona que entre en el mismo navegador vería un instante el
    // horario y las inscripciones de la anterior.
    await waitFor(() => {
      expect(queryClient.getQueryData(["auth", "perfil"])).toBeUndefined();
    });
  });
});
