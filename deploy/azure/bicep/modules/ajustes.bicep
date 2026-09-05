/*
  La configuración de la aplicación, aplicada DESPUÉS de que existan los permisos.

  ESTE MÓDULO EXISTE PARA ROMPER UN CICLO, Y EL CICLO ERA REAL

  La primera versión ponía estos ajustes dentro de `app.bicep` con un `dependsOn` hacia los
  permisos. El compilador lo rechazó, y tenía razón: los permisos necesitan el `principalId` de
  la identidad administrada, que no existe hasta que la aplicación se crea; y la aplicación
  necesitaría los permisos antes de aplicar su configuración. `app -> permisos -> app`.

  Separando la configuración, la cadena se vuelve lineal:

      app  ->  permisos  ->  ajustes

  POR QUÉ EL ORDEN IMPORTA TANTO

  Las referencias `@Microsoft.KeyVault(SecretUri=...)` las resuelve App Service AL APLICAR la
  configuración, usando la identidad administrada. Si en ese momento la identidad todavía no
  tiene permiso de lectura sobre el almacén, App Service no falla: guarda la CADENA LITERAL
  `@Microsoft.KeyVault(...)` como valor de `DATABASE_URL`.

  El síntoma es el peor posible. La aplicación arranca, intenta conectarse y falla con un error
  de PostgreSQL sobre una URL malformada. Ni el Key Vault ni los permisos aparecen mencionados
  en ninguna parte, y no hay forma de deducir la causa desde el mensaje.
*/

@description('Nombre de la aplicación a la que se aplican los ajustes.')
param nombreApp string

@description('Referencia al secreto de PostgreSQL. Es una URI, no el valor: lo resuelve App Service con su identidad.')
param referenciaBaseDeDatos string

@description('Referencia al secreto de Redis. Es una URI, no el valor.')
param referenciaRedis string

@description('Referencia al secreto de firma de tokens. Es una URI, no el valor.')
param referenciaJwt string

@description('Ambiente que se reporta en /health y decide el formato de los logs.')
param ambiente string

@description('Orígenes autorizados por CORS. Vacío significa que el navegador bloquea todas las llamadas.')
param origenesCors string

@description('Etiqueta de la imagen, que se reporta como versión en /health.')
param etiquetaImagen string

resource aplicacion 'Microsoft.Web/sites@2023-12-01' existing = {
  name: nombreApp
}

resource ajustes 'Microsoft.Web/sites/config@2023-12-01' = {
  parent: aplicacion
  name: 'appsettings'
  properties: {
    // OBLIGATORIA EN CONTENEDORES. Sin ella App Service prueba el 80 y el 8080, no encuentra a
    // uvicorn —que escucha en el 8000— y marca el sitio como caído sin más explicación.
    WEBSITES_PORT: '8000'

    // Los tres secretos. Llegan como referencia, no como valor: la contraseña de PostgreSQL
    // nunca pasa por la configuración de la aplicación ni por el historial del despliegue.
    DATABASE_URL: '@Microsoft.KeyVault(SecretUri=${referenciaBaseDeDatos})'
    REDIS_URL: '@Microsoft.KeyVault(SecretUri=${referenciaRedis})'
    JWT_SECRET: '@Microsoft.KeyVault(SecretUri=${referenciaJwt})'

    ENVIRONMENT: ambiente
    CORS_ALLOWED_ORIGINS: origenesCors
    // Apagada: `/docs` publica el contrato entero de la API, y en un ambiente que se sustenta
    // ante terceros no hace falta.
    DOCS_ENABLED: 'false'
    LOG_LEVEL: 'INFO'

    // EL POOL VA BAJO A PROPÓSITO. El límite real es `max_connections` del servidor repartido
    // entre TODAS las instancias del autoescalado. Con los valores por defecto (10+20) y las
    // seis instancias del pico serían 180 conexiones, muy por encima de lo que admite un
    // D2ds_v4: el sistema se caería justo en el momento que la sección 5 del documento quiere
    // demostrar. Con 5+10 y seis instancias son 90, que sí caben.
    DB_POOL_SIZE: '5'
    DB_MAX_OVERFLOW: '10'

    RATE_LIMIT_ENABLED: 'true'
    APP_VERSION: etiquetaImagen
  }
}
