// Configuracion plana de ESLint 9 (`eslint.config.js`), el formato que sustituyo a `.eslintrc`.
//
// La regla que sostiene todo lo demas es `@typescript-eslint/no-explicit-any` en modo error:
// `any` desactiva el sistema de tipos justo donde mas hace falta —los datos que llegan de la
// API— y convierte el modo estricto en decoracion (BEST_PRACTICES.md seccion 1).
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage", "node_modules"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommendedTypeChecked],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: {
        // Con informacion de tipos: sin ella, reglas como `no-floating-promises` —una promesa
        // sin `await` que traga el error en silencio— no pueden aplicarse.
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      "@typescript-eslint/no-explicit-any": "error",
      // Las variables sin usar son error, salvo las que empiezan por `_`: es la forma de
      // decir "recibo este parametro y no lo uso" sin que la herramienta discuta.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
  {
    // Los archivos de configuracion corren en Node y no entran en el `tsconfig` de la app.
    files: ["*.config.{js,ts}", "eslint.config.js"],
    languageOptions: { globals: globals.node },
    extends: [tseslint.configs.disableTypeChecked],
  },
);
