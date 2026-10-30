// Las alertas de LOGS de la sección 11.1 (1, 2, 3 y 6). Grupo persistente.
//
// Viven aquí y no junto a los recursos porque leen el WORKSPACE, que es persistente, y filtran
// por el `_ResourceId` de recursos efímeros. Con la demo apagada no llega ningún dato y no
// disparan; al levantarla, los recursos vuelven con el MISMO nombre (`comun/nombres.bicep`) y las
// alertas los vuelven a ver sin tocar nada.
//
// POR QUÉ LAS ALERTAS 1 Y 3 SON DE LOGS Y NO DE MÉTRICAS
//
// 11.1 pide «10 minutos sostenidos» y «tres fallos seguidos de 1 minuto». Una alerta de métricas
// con umbral estático solo admite ventanas de 1, 5, 15 o 30 minutos y no cuenta periodos
// consecutivos. Una alerta de logs sí, con `failingPeriods`: 2 periodos de 5 minutos son los 10
// sostenidos, y 3 de 1 minuto son los tres fallos seguidos. Leen la tabla `AzureMetrics`, que
// alimentan los diagnósticos de `operacion/observabilidad.bicep`.
//
// POR QUÉ LAS ALERTAS 2 Y 6 LEEN `AppServiceHTTPLogs` Y NO `AppRequests` COMO DICE 11.3
//
// `AppRequests` solo se llena si la API envía telemetría a Application Insights, y hoy no la
// envía. Sobre esa tabla las dos alertas estarían desplegadas y muertas: nunca dispararían, y su
// silencio se leería como «todo va bien». `AppServiceHTTPLogs` la escribe la plataforma por cada
// petición, con el código de respuesta en `ScStatus`, sin tocar el código. Los umbrales del
// documento no cambian. Cuando la API se instrumente, se cambia la tabla de estas dos consultas.

@description('Región de las reglas.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2.')
param tags object

@description('Identificador del workspace que leen las consultas.')
param registrosId string

@description('Identificador del grupo de acciones.')
param grupoAccionesId string

@description('Identificador del plan de App Service vigilado (alerta 1).')
param idPlan string

@description('Identificador del App Service de la API (alertas 2 y 6).')
param idApp string

@description('Identificador del Application Gateway (alerta 3).')
param idGateway string

// LAS CONSULTAS VIVEN EN `consultas/*.kql`, una por alerta, con el marcador `{{RECURSO}}` donde
// va el identificador. Así se leen y se editan como KQL, y las pruebas de `deploy/azure/pruebas`
// las ejecutan contra el workspace real para comprobar que las tablas y columnas existen. El
// identificador se compara con `=~`, que ignora mayúsculas: `_ResourceId` llega en minúsculas y el
// calculado no.
func consulta(texto string, idRecurso string) string => replace(texto, '{{RECURSO}}', idRecurso)

var reglas = [
  {
    nombre: 'saturacion-cpu'
    titulo: 'Alerta 1: saturación sostenida del plan'
    descripcion: 'CPU media del plan por encima del 85 % durante 10 minutos (dos periodos de 5). Independiente de la regla de autoescalado del 70 %.'
    severidad: 2
    consulta: consulta(loadTextContent('consultas/saturacion-cpu.kql'), idPlan)
    agregacion: 'Average'
    columna: 'Average'
    umbral: 85
    ventana: 'PT5M'
    frecuencia: 'PT5M'
    periodos: 2
  }
  {
    nombre: 'errores-api'
    titulo: 'Alerta 2: errores 5xx de la API'
    descripcion: 'Más del 5 % de respuestas 5xx en 5 minutos, con al menos 20 peticiones para que un único fallo no dispare.'
    severidad: 1
    consulta: consulta(loadTextContent('consultas/errores-api.kql'), idApp)
    agregacion: 'Count'
    columna: ''
    umbral: 0
    ventana: 'PT5M'
    frecuencia: 'PT1M'
    periodos: 1
  }
  {
    nombre: 'disponibilidad'
    titulo: 'Alerta 3: instancias no sanas tras el gateway'
    descripcion: 'La sonda del gateway (/health por 443) ve alguna instancia caída en tres minutos seguidos.'
    severidad: 1
    consulta: consulta(loadTextContent('consultas/disponibilidad.kql'), idGateway)
    agregacion: 'Minimum'
    columna: 'Minimum'
    umbral: 0
    ventana: 'PT1M'
    frecuencia: 'PT1M'
    periodos: 3
  }
  {
    nombre: 'accesos-inusuales'
    titulo: 'Alerta 6: accesos inusuales'
    descripcion: 'Más de 20 respuestas 401 o 403 en 5 minutos: intentos de entrar sin credenciales válidas o de usar un rol ajeno.'
    severidad: 2
    consulta: consulta(loadTextContent('consultas/accesos-inusuales.kql'), idApp)
    agregacion: 'Count'
    columna: ''
    umbral: 0
    ventana: 'PT5M'
    frecuencia: 'PT1M'
    periodos: 1
  }
]

resource alerta 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = [
  for r in reglas: {
    name: '${prefijo}-alerta-${r.nombre}'
    location: ubicacion
    tags: tags
    kind: 'LogAlert'
    properties: {
      displayName: r.titulo
      description: r.descripcion
      severity: r.severidad
      enabled: true
      scopes: [registrosId]
      evaluationFrequency: r.frecuencia
      windowSize: r.ventana
      criteria: {
        allOf: [
          union(
            {
              query: r.consulta
              timeAggregation: r.agregacion
              operator: 'GreaterThan'
              threshold: r.umbral
              failingPeriods: {
                numberOfEvaluationPeriods: r.periodos
                minFailingPeriodsToAlert: r.periodos
              }
            },
            // Las de `Count` cuentan filas: no tienen columna que medir.
            empty(r.columna) ? {} : { metricMeasureColumn: r.columna }
          )
        ]
      }
      // Se resuelve sola cuando la condición deja de cumplirse: una alerta de CPU que sigue
      // «activa» horas después de que la carga bajara no ayuda a nadie.
      autoMitigate: true
      actions: {
        actionGroups: [grupoAccionesId]
      }
    }
  }
]

output nombres string[] = [for (r, i) in reglas: alerta[i].name]
