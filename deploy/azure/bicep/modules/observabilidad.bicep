/*
  Envía los registros al área de trabajo persistente.

  QUÉ PROBLEMA RESUELVE

  La aplicación escribe desde hace tiempo registros en JSON con un identificador por petición,
  pensados para poder buscarlos. Pero esos registros iban a la salida estándar del contenedor y
  ahí se quedaban: visibles con `az webapp log tail` mientras alguien mirara, y perdidos en
  cuanto la instancia se reciclara.

  Con el autoescalado eso es peor de lo que parece. La petición lenta que alguien reporta
  ocurrió en una instancia que quizá ya no existe, y sin nada que la haya recogido no hay forma
  de volver a ella.

  Estos ajustes conectan la salida con el área de trabajo. Es lo que convierte «me falló la
  inscripción esta mañana» en una consulta con respuesta.

  POR QUÉ VA EN UN MÓDULO Y NO PEGADO A CADA RECURSO

  Un ajuste de diagnóstico es un recurso de EXTENSIÓN: no se declara dentro del recurso al que
  observa, sino aparte, apuntándolo con `scope`. Juntarlos aquí deja en un solo archivo la
  respuesta a «qué se está registrando», que es justo la pregunta que uno se hace cuando falta
  un dato.
*/

@description('Identificador del área de trabajo de Log Analytics. Vive en el grupo persistente.')
param registrosId string

@description('Nombre del App Service cuyos registros se recogen.')
param nombreApp string

@description('Nombre del Application Gateway. Vacío si el perfil no lo despliega.')
param nombreGateway string = ''

resource aplicacion 'Microsoft.Web/sites@2023-12-01' existing = {
  name: nombreApp
}

resource diagnosticoApp 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'a-log-analytics'
  scope: aplicacion
  properties: {
    workspaceId: registrosId
    logs: [
      {
        // LA CATEGORÍA QUE IMPORTA. En un App Service de contenedor, la salida estándar del
        // contenedor entra por aquí: es donde caen los registros JSON de la aplicación.
        category: 'AppServiceConsoleLogs'
        enabled: true
      }
      {
        // Una línea por petición HTTP, con su código de respuesta y su duración. Complementa a
        // la anterior: si la aplicación se cae antes de registrar nada, esto sigue apareciendo.
        category: 'AppServiceHTTPLogs'
        enabled: true
      }
      {
        // Lo que hace la plataforma por su cuenta: arranques, descargas de la imagen, reinicios.
        // Es donde se ve si una instancia del autoescalado no llegó a levantar.
        category: 'AppServicePlatformLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// El cortafuegos de aplicación
// ---------------------------------------------------------------------------
//
// Solo existe en el perfil de demostración, de ahí la condición.
//
// El registro del cortafuegos es lo que convierte la demostración del WAF en algo comprobable.
// Sin él, un intento de inyección bloqueado es un 403 en la pantalla y nada más; con él queda
// anotado qué regla lo detuvo y sobre qué petición, que es lo que se puede enseñar y consultar
// después.

resource gateway 'Microsoft.Network/applicationGateways@2023-09-01' existing = if (!empty(nombreGateway)) {
  name: nombreGateway
}

resource diagnosticoGateway 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = if (!empty(nombreGateway)) {
  name: 'a-log-analytics'
  scope: gateway
  properties: {
    workspaceId: registrosId
    logs: [
      {
        category: 'ApplicationGatewayAccessLog'
        enabled: true
      }
      {
        category: 'ApplicationGatewayFirewallLog'
        enabled: true
      }
    ]
  }
}

output categoriasApp int = 3
output registraGateway bool = !empty(nombreGateway)
