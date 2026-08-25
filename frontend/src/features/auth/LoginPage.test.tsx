/**
 * Pruebas del inicio de sesión.
 *
 * Se prueba lo que hace una persona —escribir, enviar, ver qué pasa— y no cómo está construido
 * el componente por dentro. Por eso los elementos se buscan por su rol y su etiqueta accesible:
 * si un test no encuentra el campo "Contraseña" por su etiqueta, es que tampoco lo encuentra
 * quien usa un lector de pantalla.
 */

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it } from "vitest";

import { AppRoutes } from "@/app/router";
import { CREDENCIALES_VALIDAS, API_URL, respuestaDeError } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { renderConProveedores } from "@/test/render";

async function entrar(email: string, password: string) {
  const usuario = userEvent.setup();

  await usuario.type(screen.getByLabelText("Correo institucional"), email);
  await usuario.type(screen.getByLabelText("Contraseña"), password);
  await usuario.click(screen.getByRole("button", { name: "Entrar" }));
}

describe("pantalla de inicio de sesión", () => {
  it("autentica y lleva a la pantalla protegida", async () => {
    renderConProveedores(<AppRoutes />, { ruta: "/login" });

    await entrar(CREDENCIALES_VALIDAS.email, CREDENCIALES_VALIDAS.password);

    // El saludo con el nombre solo aparece si el perfil se pidió CON el token: el handler de
    // MSW responde 401 si falta la cabecera de autorización.
    expect(
      await screen.findByRole("heading", { name: /Hola, Joan/, level: 1 }),
    ).toBeInTheDocument();
  });

  it("explica el fallo sin decir si el error fue el correo o la contraseña", async () => {
    renderConProveedores(<AppRoutes />, { ruta: "/login" });

    await entrar(CREDENCIALES_VALIDAS.email, "contraseña-equivocada");

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("El correo o la contraseña no son correctos.");
    // Distinguir cuál de los dos falló convertiría el formulario en una herramienta para
    // averiguar qué cuentas existen.
    expect(aviso).not.toHaveTextContent(/correo no existe|no está registrado/i);
  });

  it("explica que la cuenta está desactivada cuando el servidor lo indica", async () => {
    server.use(
      http.post(`${API_URL}/api/v1/auth/login`, () =>
        respuestaDeError(403, "USER_INACTIVE", "Cuenta desactivada"),
      ),
    );

    renderConProveedores(<AppRoutes />, { ruta: "/login" });

    await entrar(CREDENCIALES_VALIDAS.email, CREDENCIALES_VALIDAS.password);

    expect(await screen.findByRole("alert")).toHaveTextContent(/desactivada/);
  });

  it("borra la contraseña tras un fallo pero conserva el correo", async () => {
    renderConProveedores(<AppRoutes />, { ruta: "/login" });

    await entrar(CREDENCIALES_VALIDAS.email, "contraseña-equivocada");
    await screen.findByRole("alert");

    // Obligar a reescribir el correo tras un error de tecleo es una molestia gratuita.
    expect(screen.getByLabelText("Correo institucional")).toHaveValue(CREDENCIALES_VALIDAS.email);
    expect(screen.getByLabelText("Contraseña")).toHaveValue("");
  });

  it("mantiene el botón bloqueado mientras falte algún campo", async () => {
    const usuario = userEvent.setup();
    renderConProveedores(<AppRoutes />, { ruta: "/login" });

    const boton = screen.getByRole("button", { name: "Entrar" });
    expect(boton).toBeDisabled();

    await usuario.type(screen.getByLabelText("Correo institucional"), "alguien@tdea.edu.co");
    expect(boton).toBeDisabled();

    await usuario.type(screen.getByLabelText("Contraseña"), "algo");
    expect(boton).toBeEnabled();
  });

  it("permite enviar con Enter desde el campo de la contraseña", async () => {
    // Es lo que se pierde si el formulario deja de ser un `<form>` con `submit`.
    const usuario = userEvent.setup();
    renderConProveedores(<AppRoutes />, { ruta: "/login" });

    await usuario.type(
      screen.getByLabelText("Correo institucional"),
      CREDENCIALES_VALIDAS.email,
    );
    await usuario.type(
      screen.getByLabelText("Contraseña"),
      `${CREDENCIALES_VALIDAS.password}{Enter}`,
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/Hola, Joan/);
    });
  });
});
