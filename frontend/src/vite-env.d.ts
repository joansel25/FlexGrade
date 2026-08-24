/// <reference types="vite/client" />

/**
 * Tipos de las variables de entorno del frontend.
 *
 * Declararlas aquí convierte un `import.meta.env.VITE_API_BAES_URL` mal escrito en un error de
 * compilación, en vez de en un `undefined` que se descubre cuando la aplicación ya está
 * desplegada y todas las peticiones van a rutas relativas equivocadas.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
