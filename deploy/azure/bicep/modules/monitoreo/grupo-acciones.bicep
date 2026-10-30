// El grupo de acciones de la sección 11.2: a quién avisa cada alerta. Grupo persistente.
//
// Solo correo. Slack es opcional mediante Logic App y queda fuera de esta fase (11.2).

@description('Etiquetas comunes de la sección 12.2.')
param tags object

@description('Nombre del grupo de acciones.')
param nombre string

@description('Correos que reciben las alertas. Sin valor por defecto: los define el equipo (14).')
@minLength(1)
param correos string[]

resource grupoAcciones 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: nombre
  // Los grupos de acciones son globales: no tienen región.
  location: 'global'
  tags: tags
  properties: {
    // Máximo 12 caracteres: es lo que aparece como remitente en los SMS y en algunos correos.
    groupShortName: 'flexgrade'
    enabled: true
    emailReceivers: [
      for (correo, i) in correos: {
        name: 'correo-${i + 1}'
        emailAddress: correo
        // El esquema común da el mismo formato a todas las alertas, sean de métricas, de logs o
        // del registro de actividad: quien las lea no tiene que aprender tres.
        useCommonAlertSchema: true
      }
    ]
  }
}

output id string = grupoAcciones.id
