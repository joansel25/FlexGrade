// El borde: lo que da la cara a internet. Compone el gateway con WAF (`gateway.bicep`) y el
// almacenamiento del sitio estático (`frontend.bicep`). Los dos se encienden juntos con
// `desplegarBorde` porque el frontend solo tiene sentido con un punto de entrada público delante.

@description('Región.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2. Las arma `modules/comun/etiquetas.bicep`.')
param tags object

@description('Sufijo único global para los nombres que se publican en un dominio público.')
param sufijo string

@description('Subred del gateway. Tiene que ser SUYA Y SOLO SUYA: Application Gateway v2 no comparte subred con nadie.')
param subredGatewayId string

@description('Nombre de host del App Service que queda detrás del gateway.')
param hostApp string

module gateway 'gateway.bicep' = {
  name: 'gateway'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    sufijo: sufijo
    subredGatewayId: subredGatewayId
    hostApp: hostApp
  }
}

module frontend 'frontend.bicep' = {
  name: 'frontend'
  params: {
    ubicacion: ubicacion
    prefijo: prefijo
    tags: tags
    sufijo: sufijo
  }
}

output ipGateway string = gateway.outputs.ipGateway
output urlGateway string = gateway.outputs.urlGateway
output nombreGateway string = gateway.outputs.nombreGateway
output nombrePoliticaWaf string = gateway.outputs.nombrePoliticaWaf
output cuentaAlmacenamientoWeb string = frontend.outputs.cuentaAlmacenamientoWeb
output urlFrontend string = frontend.outputs.urlFrontend
