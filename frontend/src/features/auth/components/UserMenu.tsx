/**
 * Identidad de la sesión en la cabecera, con la salida.
 *
 * Muestra el nombre real del estudiante en cuanto `GET /students/me` responde, y el correo
 * mientras tanto. Ese matiz importa: tras recargar la página la sesión se recupera con el
 * refresh token, que NO devuelve quién es la persona, así que durante un instante solo se
 * conoce el correo. Mostrar un hueco vacío haría parecer que la sesión no cargó.
 */

import { Button } from "@/components/ui";
import { useAuth } from "@/features/auth/useAuth";
import { useProfile } from "@/features/auth/useProfile";

export function UserMenu() {
  const { estado, usuario, cerrarSesion } = useAuth();
  const { data: perfil } = useProfile();

  if (estado !== "autenticado") {
    return null;
  }

  const nombre = perfil?.full_name ?? usuario?.email ?? "Mi cuenta";
  const detalle = perfil ? `${perfil.program.code} · Semestre ${perfil.current_semester}` : null;

  return (
    <div className="flex items-center gap-3">
      <div className="hidden text-right leading-tight sm:block">
        <p className="text-ink-800 text-sm font-medium">{nombre}</p>
        {detalle && <p className="text-ink-500 text-xs">{detalle}</p>}
      </div>

      <Button variante="secundario" tamano="sm" onClick={() => void cerrarSesion()}>
        Salir
      </Button>
    </div>
  );
}
