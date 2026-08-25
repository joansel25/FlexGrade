/**
 * Catálogo de materias: búsqueda, filtros y paginación.
 *
 * **Por defecto se muestra el plan de estudios de la carrera del estudiante**, no el catálogo
 * completo de la institución. Antes ocurría al revés, y el resultado era una interfaz que
 * mentía: alguien de Derecho veía Programación II, abría su ficha, pulsaba «Inscribir» y solo
 * entonces recibía un `403 COURSE_NOT_IN_PROGRAM`. La regla del servidor era correcta; lo que
 * fallaba era ofrecer algo que iba a ser rechazado.
 *
 * Ver el catálogo completo sigue siendo posible, pero es una decisión explícita, y las materias
 * ajenas al plan llegan marcadas como no inscribibles desde la propia tarjeta.
 *
 * **Los filtros viven en la URL, no en el estado del componente.** El botón de atrás vuelve a
 * la búsqueda anterior en vez de salir del catálogo, recargar no pierde lo escrito, y un enlace
 * a «materias de tercer semestre» se puede copiar y compartir. Guardarlo en `useState` rompe
 * las tres cosas a la vez.
 */

import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { Alert, Button, CourseCardSkeleton, EmptyState, TextField } from "@/components/ui";
import { useProfile } from "@/features/auth/useProfile";
import { CourseCard } from "@/features/catalog/components/CourseCard";
import { Pagination } from "@/features/catalog/components/Pagination";
import { PeriodBanner } from "@/features/catalog/components/PeriodBanner";
import { useCourses, useMyProgramCourseIds, useStudyPlan } from "@/features/catalog/hooks";

/** Materias por página. Veinte llena una pantalla sin obligar a paginar constantemente. */
const TAMANO_PAGINA = 20;

/**
 * Espera antes de lanzar la búsqueda mientras se escribe.
 *
 * Sin ella, «cálculo» dispararía siete peticiones —una por letra— y las seis primeras se
 * descartarían. Multiplicado por miles de estudiantes en la ventana de matrícula, es carga
 * gratuita sobre la base de datos en el peor momento.
 */
const ESPERA_BUSQUEDA_MS = 300;

export function CatalogPage() {
  const [parametros, setParametros] = useSearchParams();
  const { data: perfil } = useProfile();
  const plan = useStudyPlan();
  const materiasDeMiPlan = useMyProgramCourseIds();

  const busquedaEnUrl = parametros.get("q") ?? "";
  const semestre = parametros.get("semestre");
  // El alcance es explícito en la URL: sin parámetro, mi carrera. `todo` es una decisión que
  // la persona toma, no un estado por defecto en el que se encuentra sin saber cómo llegó.
  const verTodo = parametros.get("alcance") === "todo";
  const pagina = Math.max(1, Number(parametros.get("pagina") ?? "1") || 1);

  // El campo de texto necesita su propio estado para responder a cada tecla sin esperar; la URL
  // se actualiza después, con retardo. Sin esta separación, escribir se sentiría lento.
  const [textoBusqueda, setTextoBusqueda] = useState(busquedaEnUrl);

  // Si la URL cambia desde fuera —botón de atrás, enlace compartido— el campo se sincroniza.
  useEffect(() => {
    setTextoBusqueda(busquedaEnUrl);
  }, [busquedaEnUrl]);

  useEffect(() => {
    if (textoBusqueda === busquedaEnUrl) {
      return;
    }

    const temporizador = setTimeout(() => {
      actualizarParametros({ q: textoBusqueda || null, pagina: null });
    }, ESPERA_BUSQUEDA_MS);

    // Cada tecla cancela el temporizador anterior: solo sobrevive la última pulsación.
    return () => {
      clearTimeout(temporizador);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [textoBusqueda, busquedaEnUrl]);

  function actualizarParametros(cambios: Record<string, string | null>) {
    const siguientes = new URLSearchParams(parametros);

    for (const [clave, valor] of Object.entries(cambios)) {
      if (valor === null || valor === "") {
        siguientes.delete(clave);
      } else {
        siguientes.set(clave, valor);
      }
    }

    // `replace` para que teclear no llene el historial: pulsar atrás debe salir del catálogo,
    // no recorrer letra a letra lo que se escribió.
    setParametros(siguientes, { replace: true });
  }

  const filtros = {
    page: pagina,
    size: TAMANO_PAGINA,
    search: busquedaEnUrl || undefined,
    semester: semestre ? Number(semestre) : undefined,
    // Aquí está el cambio de fondo: salvo que se pida lo contrario, la consulta va acotada al
    // programa del estudiante.
    program_id: verTodo ? undefined : perfil?.program.id,
  };

  // Sin el perfil todavía no se sabe qué programa acotar, y lanzar la consulta sin él traería
  // el catálogo entero un instante antes de corregirse. Esperar evita ese parpadeo.
  const listoParaConsultar = verTodo || perfil !== undefined;

  const { data, isPending, isError, error, isFetching } = useCourses(filtros);

  const hayFiltros = busquedaEnUrl !== "" || semestre !== null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-ink-900 text-2xl font-semibold tracking-tight sm:text-3xl">
          {verTodo ? "Catálogo institucional" : "Materias de mi carrera"}
        </h1>
        <p className="text-ink-600 mt-2">
          {verTodo
            ? "Todas las materias de la institución. Solo puedes inscribir las de tu plan de estudios."
            : "El plan de estudios de tu programa. Elige una materia para ver sus grupos, horarios y cupos."}
        </p>
      </header>

      <PeriodBanner />

      <ResumenDelPlan
        visible={!verTodo}
        cargando={plan.isPending}
        nombre={plan.data?.program_name}
        materias={plan.data?.courses.length}
        creditos={plan.data?.total_credits}
      />

      <section aria-label="Filtros del catálogo" className="space-y-3">
        <TextField
          etiqueta="Buscar materia"
          type="search"
          placeholder="Nombre o código, por ejemplo Cálculo o MAT101"
          value={textoBusqueda}
          onChange={(e) => setTextoBusqueda(e.target.value)}
          ayuda="La búsqueda ignora mayúsculas y tildes."
        />

        <div className="flex flex-wrap items-center gap-2">
          <FiltroRapido
            activo={!verTodo}
            onClick={() => actualizarParametros({ alcance: null, pagina: null })}
          >
            {perfil ? `Mi carrera (${perfil.program.code})` : "Mi carrera"}
          </FiltroRapido>

          <FiltroRapido
            activo={verTodo}
            onClick={() => actualizarParametros({ alcance: "todo", pagina: null })}
          >
            Todo el catálogo
          </FiltroRapido>

          <span className="bg-ink-200 mx-1 h-5 w-px" aria-hidden="true" />

          {perfil && (
            <FiltroRapido
              activo={semestre === String(perfil.current_semester)}
              onClick={() =>
                actualizarParametros({
                  semestre:
                    semestre === String(perfil.current_semester)
                      ? null
                      : String(perfil.current_semester),
                  pagina: null,
                })
              }
            >
              Semestre {perfil.current_semester}
            </FiltroRapido>
          )}

          {hayFiltros && (
            <Button
              variante="fantasma"
              tamano="sm"
              onClick={() => {
                setTextoBusqueda("");
                // Se conserva el alcance: quien está mirando todo el catálogo y limpia una
                // búsqueda no espera volver a su carrera de golpe.
                actualizarParametros({ q: null, semestre: null, pagina: null });
              }}
            >
              Limpiar filtros
            </Button>
          )}
        </div>
      </section>

      <section aria-label="Resultados">
        {(isPending || !listoParaConsultar) && <ListaCargando />}

        {isError && (
          <Alert tono="error" titulo="No se pudo cargar el catálogo">
            {error.message}
          </Alert>
        )}

        {data && data.items.length === 0 && (
          <EmptyState
            titulo={
              hayFiltros
                ? "Ninguna materia coincide con la búsqueda"
                : "Tu carrera no tiene materias cargadas"
            }
            descripcion={
              hayFiltros
                ? "Prueba con otro término, quita el filtro de semestre o busca en todo el catálogo."
                : "Comunícate con Registro Académico para que carguen el plan de estudios de tu programa."
            }
            accion={
              hayFiltros ? (
                <Button
                  variante="secundario"
                  onClick={() => {
                    setTextoBusqueda("");
                    actualizarParametros({ q: null, semestre: null, pagina: null });
                  }}
                >
                  Limpiar filtros
                </Button>
              ) : undefined
            }
          />
        )}

        {data && data.items.length > 0 && (
          <div className="space-y-6">
            {/* El resultado se anuncia a quien no ve la lista cambiar. `polite` para que espere
                a que el lector termine lo que estuviera diciendo. */}
            <p className="sr-only" role="status" aria-live="polite">
              {data.total} materias encontradas
            </p>

            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {data.items.map((materia) => (
                <li key={materia.id}>
                  <CourseCard
                    materia={materia}
                    // Solo tiene sentido advertir cuando se está viendo todo: dentro de mi
                    // carrera, todas son mías y el aviso sería ruido en cada tarjeta.
                    fueraDeMiPlan={verTodo && !materiasDeMiPlan.has(materia.id)}
                  />
                </li>
              ))}
            </ul>

            <Pagination
              pagina={data.page}
              size={data.size}
              total={data.total}
              cargando={isFetching}
              onCambiar={(siguiente) => {
                actualizarParametros({ pagina: String(siguiente) });
                // Al cambiar de página se vuelve arriba: sin esto, la página nueva empieza a
                // mitad de la lista y parece que no ha pasado nada.
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            />
          </div>
        )}
      </section>
    </div>
  );
}

/** Cifras del plan de estudios, para dar contexto a lo que se está viendo. */
function ResumenDelPlan({
  visible,
  cargando,
  nombre,
  materias,
  creditos,
}: {
  visible: boolean;
  cargando: boolean;
  nombre?: string;
  materias?: number;
  creditos?: number;
}) {
  if (!visible || cargando || nombre === undefined) {
    return null;
  }

  return (
    <p className="text-ink-500 text-sm">
      <span className="text-ink-700 font-medium">{nombre}</span> · {materias}{" "}
      {materias === 1 ? "materia" : "materias"} · {creditos}{" "}
      {creditos === 1 ? "crédito" : "créditos"} en total
    </p>
  );
}

function FiltroRapido({
  activo,
  onClick,
  children,
}: {
  activo: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      // `aria-pressed` comunica que es un interruptor y en qué posición está. Sin él, quien
      // usa lector de pantalla oye un botón sin saber si el filtro está aplicado.
      aria-pressed={activo}
      className={
        activo
          ? "bg-brand-600 rounded-full px-3 py-1.5 text-sm font-medium text-white"
          : "border-ink-300 text-ink-700 hover:bg-ink-100 rounded-full border px-3 py-1.5 text-sm font-medium transition-colors"
      }
    >
      {children}
    </button>
  );
}

function ListaCargando() {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">Cargando el catálogo…</span>
      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }, (_, indice) => (
          <li key={indice}>
            <CourseCardSkeleton />
          </li>
        ))}
      </ul>
    </div>
  );
}
