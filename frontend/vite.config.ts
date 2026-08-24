import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
// `defineConfig` se importa de `vitest/config` y no de `vite`: es la variante que ademas
// tipa el bloque `test`. Con la de `vite`, la configuracion de los tests seria un error de
// compilacion aunque funcionara en ejecucion.
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // `@/` apunta siempre a `src/`. Evita los `../../../` que aparecen en cuanto la
    // estructura por feature tiene dos niveles, y que rompen al mover un archivo.
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    port: 5173,
    // Falla si el puerto está ocupado en vez de saltar al 5174: la API autoriza el 5173
    // por CORS, así que arrancar en otro puerto daría errores de origen difíciles de leer.
    strictPort: true,
  },
  test: {
    // `happy-dom` y no `jsdom`: jsdom sustituye el `AbortController` global por el suyo, y el
    // `fetch` de Node rechaza señales que no sean de su propia clase. Con jsdom, TODA petición
    // del cliente HTTP falla en los tests con un error de interoperabilidad que no existe en
    // el navegador. happy-dom no toca esos globales, y además arranca bastante más rápido.
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      // Se mide el código propio: la configuración y los puntos de entrada no tienen
      // lógica que probar, y contarlos solo desplaza el porcentaje sin decir nada.
      exclude: ["src/main.tsx", "src/test/**", "**/*.config.*", "**/*.d.ts"],
    },
  },
});
