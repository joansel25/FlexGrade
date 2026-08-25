/**
 * Catálogo de materias: búsqueda, filtros y paginación.
 *
 * **Los filtros viven en la URL, no en el estado del componente.** Es la decisión que más se
 * nota al usar la pantalla: el botón de atrás vuelve a la búsqueda anterior en vez de salir del
 * catálogo, recargar no pierde lo escrito, y un enlace a «materias de tercer semestre» se puede
 * copiar y compartir. Guardarlo en `useState` rompe las tres cosas a la vez.
 */

import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { Alert, Button, CourseCardSkeleton, EmptyState, TextField } from "@/components/ui";
import { useProfile } from "@/features/auth/useProfile";
import { CourseCard } from "@/features/catalog/components/CourseCard";
import { Pagination } from "@/features/catalog/components/Pagination";
import { PeriodBanner } from "@/features/catalog/components/PeriodBanner";
import { useCourses } from "@/features/catalog/hooks";

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

  const busquedaEnUrl = parametros.get("q") ?? "";
  const semestre = parametros.get("semestre");
  const soloMiPrograma = parametros.get("programa") === "mio";
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
    program_id: soloMiPrograma ? perfil?.program.id : undefined,
  };

  const { data, isPending, isError, error, isFetching } = useCourses(filtros);

  const hayFiltros = busquedaEnUrl !== "" || semestre !== null || soloMiPrograma;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-ink-900 text-2xl font-semibold tracking-tight sm:text-3xl">
          Catálogo de materias
        </h1>
        <p className="text-ink-600 mt-2">
          Busca una materia y consulta sus grupos, horarios y cupos disponibles.
        </p>
      </header>

      <PeriodBanner />

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
          {perfil && (
            <FiltroRapido
              activo={soloMiPrograma}
              onClick={() =>
                actualizarParametros({ programa: soloMiPrograma ? null : "mio", pagina: null })
              }
            >
              Solo {perfil.program.code}
            </FiltroRapido>
          )}

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
                setParametros(new URLSearchParams(), { replace: true });
              }}
            >
              Limpiar filtros
            </Button>
          )}
        </div>
      </section>

      <section aria-label="Resultados">
        {isPending && <ListaCargando />}

        {isError && (
          <Alert tono="error" titulo="No se pudo cargar el catálogo">
            {error.message}
          </Alert>
        )}

        {data && data.items.length === 0 && (
          <EmptyState
            titulo="Ninguna materia coincide con la búsqueda"
            descripcion={
              hayFiltros
                ? "Prueba con otro término o quita alguno de los filtros aplicados."
                : "El catálogo está vacío para el período actual."
            }
            accion={
              hayFiltros ? (
                <Button
                  variante="secundario"
                  onClick={() => {
                    setTextoBusqueda("");
                    setParametros(new URLSearchParams(), { replace: true });
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
                  <CourseCard materia={materia} />
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
