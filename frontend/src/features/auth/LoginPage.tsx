/**
 * Pantalla de inicio de sesión.
 *
 * Es un `<form>` de verdad, con `onSubmit`, y no dos campos con un botón que llama a una
 * función. La diferencia se nota al usarlo: pulsar Enter en el campo de la contraseña envía,
 * el navegador ofrece guardar las credenciales y el gestor de contraseñas las rellena. Todo eso
 * se pierde en cuanto el envío deja de ser un `submit`.
 */

import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { Alert, Button, Card, CardBody, TextField } from "@/components/ui";
import { mensajeDeError } from "@/features/auth/mensajes";
import { useAuth } from "@/features/auth/useAuth";

interface EstadoDeRuta {
  /** Ruta a la que se quería entrar antes de que el guardián redirigiera aquí. */
  desde?: string;
}

export function LoginPage() {
  const { estado, iniciarSesion } = useAuth();
  const ubicacion = useLocation();

  const [correo, setCorreo] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const destino = (ubicacion.state as EstadoDeRuta | null)?.desde ?? "/";

  // Quien ya tiene sesión no debe ver este formulario: si llega aquí por el historial o
  // escribiendo la URL, se le devuelve a donde iba.
  if (estado === "autenticado") {
    return <Navigate to={destino} replace />;
  }

  async function alEnviar(evento: FormEvent<HTMLFormElement>) {
    // Sin esto el navegador recargaría la página enviando los datos por la URL, con la
    // contraseña visible en la barra de direcciones.
    evento.preventDefault();

    setError(null);
    setEnviando(true);

    try {
      await iniciarSesion({ email: correo.trim(), password });
      // No se navega aquí: al pasar a "autenticado", el `Navigate` de arriba se encarga. Un
      // `navigate()` manual competiría con él y podría ejecutarse antes de que el estado
      // estuviera listo.
    } catch (fallo) {
      setError(mensajeDeError(fallo));
      // La contraseña se limpia y el correo se conserva: reescribir el correo tras un fallo
      // de tecleo es una molestia gratuita.
      setPassword("");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-md flex-col justify-center py-8 sm:py-16">
      <div className="mb-8 text-center">
        <h1 className="text-ink-900 text-2xl font-semibold tracking-tight">Iniciar sesión</h1>
        <p className="text-ink-600 mt-2 text-sm">
          Entra con tu correo institucional para matricular tus materias.
        </p>
      </div>

      <Card>
        <CardBody className="space-y-5 py-6">
          {error && <Alert tono="error">{error}</Alert>}

          <form onSubmit={(e) => void alEnviar(e)} noValidate className="space-y-5">
            <TextField
              etiqueta="Correo institucional"
              type="email"
              name="email"
              // `username` y no `email`: es el valor que los gestores de contraseñas asocian
              // con la credencial guardada.
              autoComplete="username"
              inputMode="email"
              required
              autoFocus
              placeholder="estudiante@tdea.edu.co"
              value={correo}
              onChange={(e) => setCorreo(e.target.value)}
              disabled={enviando}
            />

            <TextField
              etiqueta="Contraseña"
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={enviando}
            />

            <Button
              // El único `submit` del formulario: es lo que hace que Enter funcione.
              type="submit"
              tamano="lg"
              cargando={enviando}
              // Se bloquea con los campos vacíos para no gastar una petición que el servidor
              // ya sabe que va a rechazar.
              disabled={correo.trim() === "" || password === ""}
              className="w-full"
            >
              {enviando ? "Entrando…" : "Entrar"}
            </Button>
          </form>
        </CardBody>
      </Card>

      <p className="text-ink-500 mt-6 text-center text-sm">
        ¿Problemas para entrar? Comunícate con Registro Académico.
      </p>
    </div>
  );
}
