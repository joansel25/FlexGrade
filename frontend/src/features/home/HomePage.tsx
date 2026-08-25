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
 * En su lugar va lo que este archivo llevaba prometido desde la 5.1: los accesos a las cuatro
 * pantallas del estudiante. Una pantalla de inicio que no lleva a ninguna parte obliga a
 * buscar en la barra de navegación lo que debería estar delante.
 *
 * No consulta nada nuevo. El perfil ya se pide para el saludo, y los accesos son enlaces.
 */

import { Link } from "react-router-dom";

import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui";
import { useProfile } from "@/features/auth/useProfile";

/**
 * Los cuatro destinos del estudiante, en el orden en que se recorren durante una matrícula.
 *
 * Es el mismo orden de la barra de navegación, y no por casualidad: dos ordenaciones distintas
 * para los mismos destinos obligan a releer cada vez.
 */
const ACCESOS = [
  {
    a: "/plan",
    titulo: "Mi plan de estudios",
    descripcion: "Qué llevas aprobado, qué puedes inscribir y qué te falta para graduarte.",
  },
  {
    a: "/catalogo",
    titulo: "Catálogo",
    descripcion: "Las materias de tu carrera que se ofrecen este período, con sus cupos en vivo.",
  },
  {
    a: "/mis-materias",
    titulo: "Mis materias",
    descripcion: "Lo que tienes inscrito, con la opción de cancelar y tu comprobante en PDF.",
  },
  {
    a: "/horario",
    titulo: "Horario",
    descripcion: "Tus clases de la semana, ordenadas por día y hora.",
  },
] as const;

export function HomePage() {
  const { data: perfil } = useProfile();

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-ink-900 text-2xl font-semibold tracking-tight sm:text-3xl">
          {perfil ? `Hola, ${primerNombre(perfil.full_name)}` : "Matrícula académica"}
        </h1>
        <p className="text-ink-600 mt-2 max-w-2xl">
          Inscribe tus materias, revisa tu horario y descarga tu comprobante.
        </p>
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
          {ACCESOS.map((acceso) => (
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
