

@description('Región donde se crea todo. Debe tener zonas de disponibilidad para la alta disponibilidad de PostgreSQL.')
param ubicacion string

@description('Prefijo de los nombres, para reconocer los recursos en el portal.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2. Las arma `modules/comun/etiquetas.bicep`.')
param tags object

@description('Espacio de direcciones de la VNet.')
param espacioDirecciones string = '10.0.0.0/16'

@description('''
  Si se despliega el NAT Gateway.

  ES EL RECURSO MÁS CARO DEL PERFIL ECONÓMICO, y con diferencia: 0,045 USD/hora, el 37% de la
  factura — más que Redis y más que el App Service. La cifra no es una estimación: sale de la
  facturación real de septiembre, 5,14 USD de un total de 14,02.

  Y ARQUITECTÓNICAMENTE ES PRESCINDIBLE. App Service ya ofrece un conjunto estable de
  direcciones de salida por su cuenta, consultable con `az webapp show --query
  possibleOutboundIpAddresses`. El NAT está porque lo pide la sección 3 del documento, no
  porque el sistema lo necesite para funcionar: PostgreSQL y Redis se alcanzan por red privada,
  y ninguna regla de firewall del proyecto depende de la dirección de origen.

  Lo que sí aporta es UNA dirección fija en lugar de un conjunto que Azure puede cambiar al
  escalar el plan. Si alguna vez hubiera que declarar la IP del sistema ante un tercero —una
  pasarela de pagos, un servicio de la universidad—, esto es lo que lo hace posible.

  Apagado, el perfil económico baja de 0,116 a ~0,071 USD/hora.
''')
param desplegarNat bool = true

// Los cuatro rangos del documento. Se declaran como variables y no como parámetros porque
// cambiarlos obliga a recrear la red entera: no es algo que se ajuste entre despliegues.
var subredes = {
  gateway: '10.0.1.0/24'
  app: '10.0.2.0/24'
  datos: '10.0.3.0/24'
  endpoints: '10.0.4.0/24'
  // Para las tareas de un solo uso: migraciones y seed. Necesitan subred PROPIA porque una
  // subred delegada admite un solo servicio, y las otras cuatro ya lo están o se usan para
  // puntos de conexión privados.
  tareas: '10.0.5.0/24'
}

// ---------------------------------------------------------------------------
// Grupos de seguridad: las reglas de la sección 4 del documento
// ---------------------------------------------------------------------------

resource nsgGateway 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: '${prefijo}-nsg-gateway'
  location: ubicacion
  tags: tags
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
  tags: tags
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
          // 5432 PostgreSQL. 10000 Redis: Azure Managed Redis solo escucha con TLS y en ese
          // puerto (sección 8.1). Aquí decía 6380, el puerto del Azure Cache for Redis retirado:
          // no rompía nada —la salida dentro de la VNet está permitida por defecto—, pero
          // declaraba un puerto que ya no existe en el sistema.
          destinationPortRanges: ['5432', '10000']
        }
      }
    ]
  }
}

resource nsgDatos 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: '${prefijo}-nsg-datos'
  location: ubicacion
  tags: tags
  properties: {
    securityRules: [
      {
        // La aplicación Y las tareas de un solo uso. Sin la segunda, las migraciones no
        // alcanzan el servidor y el fallo es un tiempo de espera agotado que no dice por qué.
        name: 'permitir-postgres-desde-la-app-y-las-tareas'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefixes: [subredes.app, subredes.tareas]
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
  tags: tags
  properties: {
    securityRules: [
      {
        // Redis por TLS en el 10000. Esta regla documenta la intención más que aplicarla: con
        // `privateEndpointNetworkPolicies: 'Disabled'` en la subred, Azure no evalúa el NSG
        // sobre el punto de conexión privado.
        name: 'permitir-redis-solo-desde-la-app'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: subredes.app
          sourcePortRange: '*'
          destinationAddressPrefix: subredes.endpoints
          destinationPortRange: '10000'
        }
      }
    ]
  }
}

resource nsgTareas 'Microsoft.Network/networkSecurityGroups@2023-09-01' = {
  name: '${prefijo}-nsg-tareas'
  location: ubicacion
  tags: tags
  properties: {
    securityRules: [
      {
        // Las tareas de un solo uso hablan con PostgreSQL, y nada más. No sirven tráfico y no
        // reciben nada de fuera: solo escriben el esquema y los datos de ejemplo, y mueren.
        name: 'permitir-salida-a-postgres'
        properties: {
          priority: 100
          direction: 'Outbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourceAddressPrefix: subredes.tareas
          sourcePortRange: '*'
          destinationAddressPrefix: subredes.datos
          destinationPortRange: '5432'
        }
      }
    ]
  }
}

// ---------------------------------------------------------------------------
// Salida a internet con dirección fija
// ---------------------------------------------------------------------------

resource ipSalida 'Microsoft.Network/publicIPAddresses@2023-09-01' = if (desplegarNat) {
  name: '${prefijo}-ip-salida'
  location: ubicacion
  tags: tags
  // El NAT Gateway solo admite direcciones de SKU Standard. Con Basic el despliegue falla.
  sku: { name: 'Standard' }
  properties: {
    publicIPAllocationMethod: 'Static'
  }
}

resource natGateway 'Microsoft.Network/natGateways@2023-09-01' = if (desplegarNat) {
  name: '${prefijo}-nat'
  location: ubicacion
  tags: tags
  sku: { name: 'Standard' }
  properties: {
    publicIpAddresses: [{ id: ipSalida!.id }]
    idleTimeoutInMinutes: 4
  }
}

// ---------------------------------------------------------------------------
// La VNet y sus cuatro subredes
// ---------------------------------------------------------------------------

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: '${prefijo}-vnet'
  location: ubicacion
  tags: tags
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
          // La salida de la aplicación pasa por el NAT, si lo hay: así PostgreSQL y Redis ven
          // siempre la MISMA dirección de origen. Sin él, App Service sale por su propio
          // conjunto de direcciones, que sirve igual mientras nadie tenga que declararlas.
          //
          // El `?` de la unión es lo que deja la propiedad FUERA del objeto cuando no hay NAT.
          // Ponerla en `null` no vale: ARM la interpreta como «quítale el NAT a esta subred»,
          // que aquí da lo mismo, pero en un redespliegue sobre una subred que sí lo tenía
          // provocaría una desconexión momentánea de toda la salida.
          ...(desplegarNat ? { natGateway: { id: natGateway!.id } } : {})
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
        name: 'snet-tareas'
        properties: {
          addressPrefix: subredes.tareas
          networkSecurityGroup: { id: nsgTareas.id }
          delegations: [
            {
              name: 'delegacion-container-instance'
              properties: { serviceName: 'Microsoft.ContainerInstance/containerGroups' }
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
output subredTareasId string = '${vnet.id}/subnets/snet-tareas'
// Vacía cuando no hay NAT: quien la consuma tiene que poder distinguir los dos casos.
output ipSalidaDireccion string = desplegarNat ? ipSalida!.properties.ipAddress : ''
