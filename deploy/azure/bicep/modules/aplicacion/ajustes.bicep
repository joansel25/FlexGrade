

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

@description('Cadena de conexión de Application Insights. Vacía si no hay componente al que enviar.')
param conexionAppInsights string = ''

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

    // Application Insights (11.1). Hoy la API NO envía telemetría —no tiene el SDK ni
    // OpenTelemetry—, así que esta variable no tiene efecto hasta que se instrumente. Se declara
    // ya porque es lo que el SDK lee sin más configuración, y así instrumentar la API no exige
    // tocar la infraestructura. No es un secreto: identifica a dónde enviar, no autoriza a leer.
    APPLICATIONINSIGHTS_CONNECTION_STRING: conexionAppInsights
  }
}
