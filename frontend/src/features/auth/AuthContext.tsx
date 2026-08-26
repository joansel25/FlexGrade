/**
 * Estado de la sesión, compartido por toda la aplicación.
 *
 * Resuelve tres problemas que, mal hechos, se notan justo en la ventana de matrícula:
 *
 * 1. **Recuperar la sesión al recargar.** El access token vive en memoria y se pierde con la
 *    pestaña; el refresh token sobrevive. Al arrancar se canjea uno por otro, y hasta que ese
 *    intercambio termina la aplicación NO decide si hay sesión: si lo hiciera, mandaría al
 *    login a alguien que sí la tenía.
 *
 * 2. **Renovar antes de que caduque.** El access token dura una hora. Esperar al `401` para
 *    renovar significa que una petición falla siempre —y si esa petición es la inscripción,
 *    falla en el peor momento posible—. Aquí se renueva un minuto antes del vencimiento.
 *
 * 3. **Cerrar sesión de verdad cuando el refresco falla.** Un refresh token caducado o
 *    revocado no se arregla reintentando: hay que limpiar y volver al login, sin dejar a la
 *    interfaz en un estado a medias donde parece haber sesión pero cada petición da 401.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  cerrarSesion as cerrarSesionEnApi,
  iniciarSesion as iniciarSesionEnApi,
  renovarSesion,
} from "@/features/auth/api/auth";
import type { AuthenticatedUser, LoginRequest } from "@/features/auth/api/types";
import {
  AuthContext,
  type AuthContextValue,
  type EstadoSesion,
} from "@/features/auth/authContextObject";
import {
  guardarAccessToken,
  guardarRefreshToken,
  leerAccessToken,
  leerRefreshToken,
  limpiarTokens,
} from "@/features/auth/tokenStorage";

/**
 * Margen con el que se renueva el token antes de que caduque.
 *
 * Un minuto es suficiente para que la renovación termine incluso con la red lenta del pico de
 * matrícula, y lo bastante corto como para no renovar constantemente.
 */
const MARGEN_RENOVACION_MS = 60_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const [estado, setEstado] = useState<EstadoSesion>("cargando");
  const [usuario, setUsuario] = useState<AuthenticatedUser | null>(null);
  // El token también en estado, y no solo en el módulo de almacenamiento: los componentes
  // tienen que volver a pintarse cuando cambia. Guardarlo únicamente fuera de React haría que
  // una pantalla siguiera usando el token viejo tras una renovación.
  const [accessToken, setAccessToken] = useState<string | null>(null);

  const temporizadorRenovacion = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancelarRenovacionProgramada = useCallback(() => {
    if (temporizadorRenovacion.current !== null) {
      clearTimeout(temporizadorRenovacion.current);
      temporizadorRenovacion.current = null;
    }
  }, []);

  const terminarSesion = useCallback(() => {
    cancelarRenovacionProgramada();
    limpiarTokens();
    setAccessToken(null);
    setUsuario(null);
    setEstado("anonimo");
    // Se vacía la caché de consultas: contiene el horario y las inscripciones de quien acaba
    // de salir, y dejarla viva se los mostraría a la siguiente persona que entre en el mismo
    // navegador antes de que lleguen sus propios datos.
    queryClient.clear();
  }, [cancelarRenovacionProgramada, queryClient]);

  /**
   * Aplica un par de tokens recién obtenido y programa la siguiente renovación.
   *
   * `useRef` para la función porque se llama a sí misma a través del temporizador: una función
   * normal capturaría la versión de este render y, tras la primera renovación, la cadena se
   * rompería en silencio; la sesión caducaría una hora después sin que nadie lo entendiera.
   */
  const aplicarTokensRef = useRef<(tokens: {
    access_token: string;
    refresh_token: string;
    expires_in: number;
  }) => void>(() => undefined);

  const renovar = useCallback(async () => {
    const refresh = leerRefreshToken();

    if (refresh === null) {
      terminarSesion();
      return;
    }

    try {
      const tokens = await renovarSesion(refresh);
      aplicarTokensRef.current(tokens);
      // La renovación periódica también refresca el rol: si a alguien se lo cambian a mitad de
      // sesión, la interfaz deja de ofrecerle lo que ya no le corresponde sin esperar a que
      // cierre sesión.
      setUsuario(tokens.user);
    } catch {
      // Un refresco fallido no se reintenta: si el token ya no vale, no va a valer en dos
      // segundos. Se cierra la sesión y la persona vuelve a entrar.
      terminarSesion();
    }
  }, [terminarSesion]);

  aplicarTokensRef.current = (tokens) => {
    guardarAccessToken(tokens.access_token);
    // El refresh token se ROTA en cada renovación: guardar el nuevo no es opcional, el
    // anterior deja de servir.
    guardarRefreshToken(tokens.refresh_token);
    setAccessToken(tokens.access_token);

    cancelarRenovacionProgramada();

    // `expires_in` llega en segundos. Si fuera tan corto que el margen lo deja en negativo, se
    // renueva de inmediato en vez de programar un temporizador en el pasado.
    const esperaMs = Math.max(tokens.expires_in * 1000 - MARGEN_RENOVACION_MS, 0);

    temporizadorRenovacion.current = setTimeout(() => {
      void renovar();
    }, esperaMs);
  };

  // Recuperación de la sesión al cargar la aplicación.
  useEffect(() => {
    const refresh = leerRefreshToken();

    if (refresh === null) {
      setEstado("anonimo");
      return;
    }

    let cancelado = false;

    void (async () => {
      try {
        const tokens = await renovarSesion(refresh);

        if (cancelado) {
          return;
        }

        aplicarTokensRef.current(tokens);
        // El refresco SÍ devuelve la cuenta, y aquí está la razón de que lo haga: esta rama es
        // la que restaura la sesión al recargar la página. Sin el `user`, se recuperaría el
        // acceso sin saber con qué rol, y las rutas de administración expulsarían a un
        // administrador legítimo en cuanto refrescara la pestaña.
        setUsuario(tokens.user);
        setEstado("autenticado");
      } catch {
        if (!cancelado) {
          terminarSesion();
        }
      }
    })();

    return () => {
      cancelado = true;
    };
    // Solo al montar: es la recuperación inicial, no algo que deba repetirse en cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Al desmontar se cancela el temporizador pendiente, para no dejar una renovación viva
  // apuntando a un componente que ya no existe.
  useEffect(() => cancelarRenovacionProgramada, [cancelarRenovacionProgramada]);

  const iniciarSesion = useCallback(
    async (credenciales: LoginRequest) => {
      const respuesta = await iniciarSesionEnApi(credenciales);

      aplicarTokensRef.current(respuesta);
      setUsuario(respuesta.user);
      setEstado("autenticado");
    },
    [],
  );

  const cerrarSesion = useCallback(async () => {
    const token = leerAccessToken();

    if (token !== null) {
      // Si la llamada falla —red caída, token ya caducado— se sigue adelante igualmente: lo
      // que de verdad cierra la sesión es descartar los tokens en el cliente, y dejar a
      // alguien "dentro" porque el servidor no contestó sería lo peor de los dos mundos.
      await cerrarSesionEnApi(token).catch(() => undefined);
    }

    terminarSesion();
  }, [terminarSesion]);

  const valor = useMemo<AuthContextValue>(
    () => ({ estado, usuario, accessToken, iniciarSesion, cerrarSesion }),
    [estado, usuario, accessToken, iniciarSesion, cerrarSesion],
  );

  return <AuthContext.Provider value={valor}>{children}</AuthContext.Provider>;
}
