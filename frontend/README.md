# Frontend — FlexGrade

SPA de matrícula académica: React 18 + TypeScript + Vite. Consume la API REST del backend
descrita en `matricula_docs/docs/API.md`.

## Arrancar en local

El backend tiene que estar levantado (`docker-compose up -d` en la raíz del repositorio).

```bash
cd frontend
npm install
cp .env.example .env.local     # VITE_API_BASE_URL=http://localhost:8000
npm run dev                    # http://localhost:5173
```

El puerto 5173 no es casual: es el único origen que la API autoriza por CORS en desarrollo
(`CORS_ALLOWED_ORIGINS` en `docker-compose.yml`). Por eso Vite arranca con `strictPort`: si el
puerto estuviera ocupado y saltara al 5174, todas las llamadas fallarían por origen no
autorizado, con un error de navegador que no dice eso en ninguna parte.

Si en la cabecera aparece **«Sin conexión»**, el backend no está respondiendo: revísalo con
`curl http://localhost:8000/health`.

Para entrar necesitas una cuenta. Las del seed (`make seed` en la raíz) sirven:
`estudiante01@tdea.edu.co` / `SecurePass123`.

## Comandos

| Comando | Qué hace |
|---|---|
| `npm run dev` | Servidor de desarrollo con recarga en caliente |
| `npm run build` | Comprueba tipos y compila a `dist/` |
| `npm run lint` | ESLint con reglas que usan información de tipos |
| `npm run type-check` | Solo TypeScript, sin compilar |
| `npm test` | Tests una vez (lo que ejecuta el CI) |
| `npm run test:watch` | Tests en modo observación |
| `npm run format` | Prettier |

Son exactamente los que ejecuta `frontend-ci` en `.github/workflows/ci.yml`. Ese job se activó
solo al crearse `frontend/package.json`.

## Cómo está organizado

```
src/
├── app/           Estructura de la aplicación: proveedores, rutas y layout
├── components/ui/ Piezas visuales reutilizables (Button, Card, StatusDot)
├── features/      Una carpeta por funcionalidad, con su API, sus hooks y sus pantallas
├── lib/           Cliente HTTP, errores de la API y configuración de TanStack Query
└── test/          Utilidades de prueba: MSW y el render con proveedores
```

**Por feature, no por tipo de archivo.** Una carpeta `hooks/` con veinte hooks de cinco
funcionalidades distintas obliga a saltar entre cuatro carpetas para entender una pantalla.
Aquí, todo lo que necesita el catálogo vive en `features/catalog/`, y borrar una funcionalidad
es borrar una carpeta.

`@/` apunta siempre a `src/`: `import { Button } from "@/components/ui"` en vez de contar
`../../..` y romperlo al mover el archivo.

## Decisiones que conviene conocer antes de tocar el código

**El estado del servidor lo gestiona TanStack Query, no `useState`.** Los datos que vienen de la
API tienen caché, revalidación, reintentos y estados de carga; reimplementarlos a mano en cada
pantalla es de donde salen los spinners que no se apagan.

**Los cupos nunca se cachean.** Es la misma regla del backend (`CLAUDE.md`): el catálogo puede
considerarse fresco 30 segundos, la disponibilidad de un grupo no. Un número de cupos guardado
hace que la interfaz mienta justo cuando más importa. En `lib/query/queryClient.ts` están las
dos constantes que lo expresan.

**Las mutaciones no se reintentan solas.** Inscribir dos veces por un reintento automático es
exactamente el problema que el sistema entero existe para evitar.

**Los errores se deciden por `code`, nunca por el mensaje.** `API.md` garantiza estables los
`error.code`; el `message` puede cambiar de redacción. Un `409 COURSE_CAPACITY_EXCEEDED` no es
una avería: es "alguien se te adelantó", y la interfaz debe refrescar cupos y ofrecer otro grupo.

**Los tokens: access en memoria, refresh en `localStorage`.** El access token firma cada
petición, así que es el que más daño hace si se filtra: al vivir en una variable de módulo, un
script inyectado no tiene forma de leerlo. El refresh token sí se persiste, porque si no,
recargar la pestaña cerraría la sesión en mitad de la matrícula. La alternativa impecable
—cookie `httpOnly`— se descartó porque Azure Front Door y el balanceador son dominios distintos y
sería una cookie de terceros, bloqueada por defecto en Safari y Firefox. Todo esto está
explicado en `features/auth/tokenStorage.ts`, que es el único archivo a reescribir si algún día
se unifican los dominios.

**La sesión se renueva un minuto antes de caducar.** Esperar al `401` para renovar significa que
una petición falla siempre; si esa petición es la inscripción, falla en el peor momento.

**`RequireAuth` no es seguridad.** Cualquiera puede saltárselo editando el JavaScript de su
navegador. Lo que protege de verdad son los guardianes del backend. Existe para que la interfaz
no mienta: sin él, alguien sin sesión vería pantallas vacías llenándose de errores 401 en vez de
una invitación clara a entrar.

**Accesibilidad desde el principio.** Elementos nativos (`button`, `nav`, `main`), foco visible
en todo lo enfocable, enlace para saltar al contenido y estados que nunca se comunican solo con
color. Añadirlo después cuesta diez veces más que hacerlo así.

## Tests

Vitest + Testing Library, con MSW interceptando la red. Se prueba lo que hace la aplicación
—«muestra el ambiente cuando la API responde»— y no cómo está escrita por dentro.

MSW intercepta a nivel de red en vez de sustituir `fetch` por un doble, así que el cliente HTTP
real se ejerce de verdad: cabeceras, códigos de estado e interpretación del cuerpo de error.

`.env.test` sí se versiona: no contiene secretos y el runner del CI no tiene ningún `.env.local`.
Su URL debe coincidir con la de `src/test/msw/handlers.ts`.

## Despliegue

`npm run build` genera `dist/`, que son archivos estáticos: van a Azure Storage y se distribuyen por
Azure Front Door. `VITE_API_BASE_URL` se resuelve **en tiempo de build**, no de ejecución, así que
cada ambiente se construye con la URL de su API.
