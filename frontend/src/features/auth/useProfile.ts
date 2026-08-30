/**
 * Perfil del estudiante autenticado.
 *
 * Se consulta aparte del login por una razón concreta: al recuperar la sesión con el refresh
 * token, la API devuelve tokens pero NO el bloque `user` (`API.md`). Sin esta consulta, tras
 * recargar la página habría sesión pero no se sabría de quién.
 *
 * Además comprueba algo que el token por sí solo no puede: que la cuenta siga activa y con
 * perfil académico. Un token válido de una cuenta desactivada recibe aquí un 403.
 *
 * **Solo se pregunta si quien entra es ESTUDIANTE.** `GET /students/me` responde
 * `404 STUDENT_PROFILE_NOT_FOUND` a cualquier otro rol, así que sin esta guarda cada carga de
 * un administrador o un docente gastaba una petición para recibir un error previsible. No
 * rompía nada —los consumidores tratan la ausencia de perfil— y por eso pasó desapercibido:
 * era ruido silencioso, del que solo se entera quien mira la consola del navegador.
 */

import { useQuery } from "@tanstack/react-query";

import { CLAVE_PERFIL, obtenerPerfil } from "@/features/auth/api/auth";
import { useAuth } from "@/features/auth/useAuth";

export function useProfile() {
  const { accessToken, estado, usuario } = useAuth();

  return useQuery({
    queryKey: CLAVE_PERFIL,
    queryFn: ({ signal }) => {
      if (accessToken === null) {
        // No deberia ocurrir: `enabled` ya lo impide. La comprobacion existe para que el tipo
        // sea `string` dentro de la llamada, sin una asercion que mienta al compilador.
        throw new Error("No hay sesión activa");
      }

      return obtenerPerfil(accessToken, signal);
    },
    // Sin sesion no se pregunta. Sin esta guarda, la consulta se dispararia en la pantalla de
    // login y produciria un 401 en cada carga. Y solo para estudiantes: al resto el endpoint
    // les responde 404, porque no tienen perfil academico que devolver.
    enabled: estado === "autenticado" && accessToken !== null && usuario?.role === "STUDENT",
    // El perfil cambia como mucho una vez por semestre: no tiene sentido revalidarlo al volver
    // a la pestaña, como si lo tiene con los cupos.
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
  });
}
