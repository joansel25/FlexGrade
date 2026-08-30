/**
 * Pantalla de inicio: dónde aterriza el estudiante al entrar.
 *
 * Hasta la iteración 6.4 mostraba un recuadro con el estado de la API, su ambiente y su
 * versión. Era andamiaje de la 5.1 —servía para distinguir «la API está caída» de «mi código
 * está mal» cuando todavía no había pantallas reales— y se quedó puesto. Ese dato no le sirve
 * al estudiante: no puede hacer nada con él, y ver «dev» o un número de versión en la primera
 * pantalla de su matrícula solo genera desconfianza. Cuando la API falla, quien lo tiene que
 * decir es la operación que falló, con lo que hay que hacer al respecto; eso ya lo hace
 * `mensajes.ts` en cada flujo.
 *
 * En su lugar va lo que este archivo llevaba prometido desde la 5.1: los accesos a las
 * pantallas de quien entra. Una pantalla de inicio que no lleva a ninguna parte obliga a
 * buscar en la barra de navegación lo que debería estar delante.
 *
 * **Los accesos se filtran POR ROL, y hasta una prueba manual no lo hacían.** La barra de
 * navegación filtra desde la Fase 9; esta pantalla se quedó atrás, así que un administrador
 * veía las cinco pantallas del estudiante y al pulsar cualquiera recibía
 * `STUDENT_PROFILE_NOT_FOUND` —un error que parece del sistema y es del menú—. Los destinos
 * salen ahora de `app/destinos.ts`, la MISMA lista que usa la barra: con una sola fuente,
 * añadir un destino es imposible de hacer a medias.
 *
 * No consulta nada nuevo. El perfil ya se pide para el saludo, y los accesos son enlaces.
 */

import { Link } from "react-router-dom";

import type { UserRole } from "@/features/auth/api/types";

import { destinosDe } from "@/app/destinos";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { useAuth } from "@/features/auth/useAuth";
import { useProfile } from "@/features/auth/useProfile";

/**
 * Qué se anuncia bajo el saludo, según quién entra.
 *
 * «Inscribe tus materias, revisa tu horario y descarga tu comprobante» era el único texto, y a
 * quien administra o dicta le describe un trabajo que no es el suyo. La clave `SIN_ROL` cubre
 * la sesión todavía sin resolver: un texto neutro es mejor que prometer lo que quizá no
 * corresponda.
 */
const SUBTITULOS: Record<UserRole | "SIN_ROL", string> = {
  STUDENT: "Inscribe tus materias, revisa tu horario y descarga tu comprobante.",
  PROFESSOR: "Consulta los grupos que dictas y registra las notas de tus estudiantes.",
  ADMIN: "Gestiona las ventanas de matrícula, el catálogo académico y los reportes.",
  SIN_ROL: "Bienvenido al sistema de matrícula.",
};

export function HomePage() {
  const { data: perfil } = useProfile();
  const { usuario } = useAuth();
  const rol = usuario?.role ?? null;

  // El destino a esta misma pantalla se descarta: una tarjeta que lleva donde ya estás no es un
  // acceso, es ruido.
  const accesos = destinosDe(rol).filter((destino) => destino.a !== "/");

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-ink-900 text-2xl font-semibold tracking-tight sm:text-3xl">
          {perfil ? `Hola, ${primerNombre(perfil.full_name)}` : "Matrícula académica"}
        </h1>
        <p className="text-ink-600 mt-2 max-w-2xl">{SUBTITULOS[rol ?? "SIN_ROL"]}</p>
      </section>

      {perfil && (
        <section aria-labelledby="datos-academicos">
          <Card className="max-w-xl">
            <CardHeader>
              <CardTitle id="datos-academicos">Tus datos académicos</CardTitle>
            </CardHeader>
            <CardBody>
              <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
                <dt className="text-ink-500">Código</dt>
                <dd className="text-ink-800 font-medium">{perfil.student_code}</dd>
                <dt className="text-ink-500">Programa</dt>
                <dd className="text-ink-800 font-medium">{perfil.program.name}</dd>
                <dt className="text-ink-500">Semestre</dt>
                <dd className="text-ink-800 font-medium">{perfil.current_semester}</dd>
              </dl>
            </CardBody>
          </Card>
        </section>
      )}

      <section aria-labelledby="accesos" className="space-y-3">
        <h2 id="accesos" className="text-ink-900 text-lg font-semibold">
          Qué quieres hacer
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2">
          {accesos.map((acceso) => (
            <li key={acceso.a}>
              <Link
                to={acceso.a}
                className="focus-visible:outline-brand-600 rounded-card block h-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <Card className="hover:border-brand-300 h-full transition-colors">
                  <CardBody className="space-y-1">
                    <p className="text-ink-900 font-medium">{acceso.titulo}</p>
                    <p className="text-ink-600 text-sm">{acceso.descripcion}</p>
                  </CardBody>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

/**
 * Primer nombre de la persona, para el saludo.
 *
 * Saludar con el nombre completo —incluidos los dos apellidos— suena a carta oficial, no a una
 * aplicación que la persona usa cada semestre.
 */
function primerNombre(nombreCompleto: string): string {
  return nombreCompleto.trim().split(" ")[0] ?? nombreCompleto;
}
