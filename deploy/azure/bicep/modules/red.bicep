/*
  Red: VNet, subredes, NSG y salida a internet.

  Es lo primero que se despliega y lo que todo lo demás necesita: PostgreSQL se inyecta en una
  subred delegada, el App Service se integra en otra, y el Application Gateway vive en la
  pública. Cambiar el direccionamiento después obliga a recrear los tres.

  DOS COSAS DEL DOCUMENTO DE LA FASE I QUE NO SE TRADUCEN LITERALES

  1. «Subred de respaldo para el standby de PostgreSQL» no existe en Azure. La alta
     disponibilidad con redundancia de zona coloca la réplica en OTRA ZONA de disponibilidad,
     usando la MISMA subred delegada. No hay nada que reservarle. En su lugar, el cuarto
     espacio de direcciones se usa para los puntos de conexión privados —hoy Redis—, que sí
     necesitan una subred propia porque la de PostgreSQL está delegada en exclusiva.

  2. «App Gateway -> App: 8000» tampoco. El 8000 es el puerto INTERNO del contenedor
     (`WEBSITES_PORT`); App Service publica siempre por 443. El aislamiento se consigue con
     restricciones de acceso, no abriendo un puerto.

  POR QUÉ LAS SUBREDES VAN DENTRO DEL RECURSO DE LA VNet Y NO COMO RECURSOS APARTE

  Declararlas como `Microsoft.Network/virtualNetworks/subnets` sueltas provoca una carrera
  conocida: dos despliegues seguidos pueden sobrescribirse las subredes entre sí, y el síntoma
  es una subred que desaparece sin que nadie la haya tocado.
*/

@description('Región donde se crea todo. Debe tener zonas de disponibilidad para la alta disponibilidad de PostgreSQL.')
param ubicacion string

@description('Prefijo de los nombres, para reconocer los recursos en el portal.')
param prefijo string

@description('Espacio de direcciones de la VNet.')
param espacioDirecciones string = '10.0.0.0/16'

// Los cuatro rangos del documento. Se declaran como variables y no como parámetros porque
// cambiarlos obliga a recrear la red entera: no es algo que se ajuste entre despliegues.
var subredes = {
  gateway: '10.0.1.0/24'
  app: '10.0.2.0/24'
  datos: '10.0.3.0/24'
  endpoints: '10.0.4.0/24'
}

// ---------------------------------------------------------------------------
// Grupos de seguridad: las reglas de la sección 4 del documento
// ---------------------------------------------------------------------------

resource nsgGateway 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: '${prefijo}-nsg-gateway'
  location: ubicacion
  properties: {
    securityRules: [
      {
        name: 'permitir-http-desde-internet'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'Internet'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRanges: ['80', '443']
        }
      }
      {
        // OBLIGATORIA Y NO NEGOCIABLE. Application Gateway v2 recibe en estos puertos las
        // órdenes del plano de control de Azure. Sin esta regla el despliegue del gateway
        // FALLA, y el mensaje no menciona el NSG por ningún lado: es el error más difícil de
        // diagnosticar de todo el montaje.
        name: 'permitir-gestion-del-gateway'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: 'GatewayManager'
          sourcePortRange: '*'
          destinationAddressPrefix: '*'
          destinationPortRange: '65200-65535'
        }
      }
    ]
  }
}

resource nsgApp 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: '${prefijo}-nsg-app'
  location: ubicacion
  properties: {
    securityRules: [
      {
        // La aplicación solo habla con la capa de datos. La entrada la controla el App Service
        // con sus restricciones de acceso, no este NSG: la integración con VNet es de SALIDA.
        name: 'permitir-salida-a-datos'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: subredes.app
          sourcePortRange: '*'
          destinationAddressPrefixes: [subredes.datos, subredes.endpoints]
          // 5432 PostgreSQL. 6380 Redis: Azure Cache exige TLS y NO escucha en el 6379 que
          // dice el documento —el puerto sin cifrar viene deshabilitado y así se queda—.
          destinationPortRanges: ['5432', '6380']
        }
      }
    ]
  }
}

resource nsgDatos 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: '${prefijo}-nsg-datos'
  location: ubicacion
  properties: {
    securityRules: [
      {
        name: 'permitir-postgres-solo-desde-la-app'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: subredes.app
          sourcePortRange: '*'
          destinationAddressPrefix: subredes.datos
          destinationPortRange: '5432'
        }
      }
      {
        // Lo que hace real el aislamiento. Sin esta regla, el NSG por defecto permite el
        // tráfico entre subredes de la misma VNet y la subred «privada» no protege de nada.
        name: 'denegar-el-resto'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourceAddressPrefix: 'VirtualNetwork'
          sourcePortRange: '*'
          destinationAddressPrefix: subredes.datos
          destinationPortRange: '*'
        }
      }
    ]
  }
}

resource nsgEndpoints 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: '${prefijo}-nsg-endpoints'
  location: ubicacion
  properties: {
    securityRules: [
      {
        name: 'permitir-redis-solo-desde-la-app'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: subredes.app
          sourcePortRange: '*'
          destinationAddressPrefix: subredes.endpoints
          destinationPortRange: '6380'
        }
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// Salida a internet con dirección fija
// ---------------------------------------------------------------------------

resource ipSalida 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: '${prefijo}-ip-salida'
  location: ubicacion
  // El NAT Gateway solo admite direcciones de SKU Standard. Con Basic el despliegue falla.
  sku: { name: 'Standard' }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource natGateway 'Microsoft.Network/natGateways@2023-09-01' = {
  name: '${prefijo}-nat'
  location: ubicacion
  sku: { name: 'Standard' }
  properties: {
    publicIpAddresses: [{ id: ipSalida.id }]
    idleTimeoutInMinutes: 4
  }
}

// ---------------------------------------------------------------------------
// La VNet y sus cuatro subredes
// ---------------------------------------------------------------------------

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: '${prefijo}-vnet'
  location: ubicacion
  properties: {
    addressSpace: { addressPrefixes: [espacioDirecciones] }
    subnets: [
      {
        name: 'snet-gateway'
        properties: {
          addressPrefix: subredes.gateway
          networkSecurityGroup: { id: nsgGateway.id }
        }
      }
      {
        name: 'snet-app'
        properties: {
          addressPrefix: subredes.app
          networkSecurityGroup: { id: nsgApp.id }
          // La salida de la aplicación pasa por el NAT: así PostgreSQL y Redis ven siempre la
          // MISMA dirección de origen, y las reglas de firewall se pueden escribir.
          natGateway: { id: natGateway.id }
          // La integración de App Service con VNet exige la subred delegada y en exclusiva.
          delegations: [
            {
              name: 'delegacion-app-service'
              properties: { serviceName: 'Microsoft.Web/serverFarms' }
            }
          ]
        }
      }
      {
        name: 'snet-datos'
        properties: {
          addressPrefix: subredes.datos
          networkSecurityGroup: { id: nsgDatos.id }
          // Delegada a PostgreSQL Flexible Server. Una subred delegada NO admite ningún otro
          // recurso: por eso Redis necesita la suya, aunque el documento los ponga juntos.
          delegations: [
            {
              name: 'delegacion-postgres'
              properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' }
            }
          ]
        }
      }
      {
        name: 'snet-endpoints'
        properties: {
          addressPrefix: subredes.endpoints
          networkSecurityGroup: { id: nsgEndpoints.id }
          // Aquí aterriza el punto de conexión privado de Redis. Es el espacio que el documento
          // reservaba para el standby de PostgreSQL, que resultó no necesitar ninguno.
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

// Las subredes se referencian POR NOMBRE y no por su posición en el array. Con índices, meter
// una subred nueva en medio de la lista reasigna en silencio todas las salidas siguientes: la
// aplicación acabaría integrada en la subred de datos sin que nada fallara al desplegar.
output vnetId string = vnet.id
output vnetNombre string = vnet.name
output subredGatewayId string = '${vnet.id}/subnets/snet-gateway'
output subredAppId string = '${vnet.id}/subnets/snet-app'
output subredDatosId string = '${vnet.id}/subnets/snet-datos'
output subredEndpointsId string = '${vnet.id}/subnets/snet-endpoints'
output ipSalidaDireccion string = ipSalida.properties.ipAddress
