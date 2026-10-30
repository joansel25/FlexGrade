@description('Región.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2. Las arma `modules/comun/etiquetas.bicep`.')
param tags object

@description('Sufijo único global: da nombre a la etiqueta DNS pública del gateway.')
param sufijo string

@description('Subred del gateway. Tiene que ser SUYA Y SOLO SUYA: Application Gateway v2 no comparte subred con nadie.')
param subredGatewayId string

@description('Nombre de host del App Service que queda detrás del gateway.')
param hostApp string

@description('Unidades de capacidad mínimas. Cada una son 0,0144 USD/hora.')
@minValue(1)
@maxValue(10)
param capacidadMinima int = 1

@description('Unidades de capacidad máximas a las que el gateway puede crecer solo.')
@minValue(2)
@maxValue(20)
param capacidadMaxima int = 3

@description('Modo del WAF. `Prevention` bloquea; `Detection` solo anota, y sirve para comprobar que ninguna regla estorba a la aplicación antes de activarla de verdad.')
@allowed(['Prevention', 'Detection'])
param modoWaf string = 'Prevention'

import { nombresEfimeros } from '../comun/nombres.bicep'

// Los nombres salen de la función compartida: las alertas del grupo persistente vigilan
// estos recursos por su identificador, calculado con el mismo cálculo.
var nombres = nombresEfimeros(prefijo, sufijo)

// ---------------------------------------------------------------------------
// La dirección pública
// ---------------------------------------------------------------------------
//
// `Standard` + `Static` no son preferencias: Application Gateway v2 RECHAZA cualquier otra
// combinación. Una IP básica o dinámica hace fallar el despliegue después de haber creado el
// resto.

resource ipPublica 'Microsoft.Network/publicIPAddresses@2023-09-01' = {
  name: '${prefijo}-ip-gateway'
  location: ubicacion
  tags: tags
  sku: {
    name: 'Standard'
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    dnsSettings: {
      // Da un nombre estable `matricula-<sufijo>.<region>.cloudapp.azure.com`. Sin él solo
      // queda la dirección numérica, que cambia en cada despliegue y hay que ir a buscar al
      // portal antes de poder enseñar nada.
      domainNameLabel: '${prefijo}-${sufijo}'
    }
  }
}

// ---------------------------------------------------------------------------
// La política de WAF
// ---------------------------------------------------------------------------
//
// Va en un recurso APARTE y no dentro del gateway. Las reglas embebidas están obsoletas desde
// hace varias versiones de API, y una política separada se puede cambiar —de `Prevention` a
// `Detection`, por ejemplo— sin volver a desplegar el gateway, que tarda veinte minutos.

resource politicaWaf 'Microsoft.Network/ApplicationGatewayWebApplicationFirewallPolicies@2023-09-01' = {
  name: '${prefijo}-waf'
  location: ubicacion
  tags: tags
  properties: {
    policySettings: {
      state: 'Enabled'
      mode: modoWaf
      // El cuerpo se inspecciona hasta este tamaño. La aplicación no recibe cargas grandes: la
      // petición mayor es una inscripción, que son unos pocos identificadores.
      maxRequestBodySizeInKb: 128
      fileUploadLimitInMb: 10
      requestBodyCheck: true
    }
    managedRules: {
      managedRuleSets: [
        {
          // OWASP 3.2: inyección SQL, XSS, recorrido de directorios y el resto del top 10. Es
          // el conjunto que se espera cuando un documento dice «WAF» sin más detalle.
          ruleSetType: 'OWASP'
          ruleSetVersion: '3.2'
        }
      ]
    }
  }
}

// ---------------------------------------------------------------------------
// El gateway
// ---------------------------------------------------------------------------
//
// Los nombres de las partes internas se repiten como identificadores completos porque ARM no
// deja referenciar un hijo antes de que el padre exista. `resourceId(...)` construye el
// identificador sin crear dependencia, que es la forma habitual de resolverlo en este recurso.

var idGateway = resourceId('Microsoft.Network/applicationGateways', nombres.gateway)

resource gateway 'Microsoft.Network/applicationGateways@2023-09-01' = {
  name: nombres.gateway
  location: ubicacion
  tags: tags
  properties: {
    sku: {
      name: 'WAF_v2'
      tier: 'WAF_v2'
      // Sin `capacity`: lo fija `autoscaleConfiguration`. Declarar los dos a la vez es un error
      // de despliegue.
    }
    autoscaleConfiguration: {
      minCapacity: capacidadMinima
      maxCapacity: capacidadMaxima
    }
    firewallPolicy: {
      id: politicaWaf.id
    }
    gatewayIPConfigurations: [
      {
        name: 'configuracion-ip'
        properties: {
          subnet: {
            id: subredGatewayId
          }
        }
      }
    ]
    frontendIPConfigurations: [
      {
        name: 'frontal-publico'
        properties: {
          publicIPAddress: {
            id: ipPublica.id
          }
        }
      }
    ]
    frontendPorts: [
      {
        name: 'puerto-80'
        properties: {
          port: 80
        }
      }
    ]
    backendAddressPools: [
      {
        name: 'grupo-api'
        properties: {
          backendAddresses: [
            {
              // El nombre DNS del App Service, no su dirección: App Service está detrás de un
              // balanceador compartido y su IP cambia sin avisar.
              fqdn: hostApp
            }
          ]
        }
      }
    ]
    probes: [
      {
        name: 'sonda-salud'
        properties: {
          protocol: 'Https'
          // `/health` y NO `/health/ready`. La segunda comprueba PostgreSQL y Redis: si la base
          // de datos parpadea, el gateway retiraría del balanceo instancias que están
          // perfectamente vivas y el corte sería mayor que la causa.
          path: '/health'
          interval: 30
          timeout: 30
          unhealthyThreshold: 3
          // En una SONDA la propiedad se llama distinto que en los ajustes del backend, aunque
          // haga lo mismo: toma el `Host` del FQDN del grupo de backend.
          pickHostNameFromBackendHttpSettings: true
          match: {
            statusCodes: ['200-399']
          }
        }
      }
    ]
    backendHttpSettingsCollection: [
      {
        name: 'ajustes-api'
        properties: {
          port: 443
          protocol: 'Https'
          cookieBasedAffinity: 'Disabled'
          // Sin afinidad de sesión A PROPÓSITO. La API no guarda estado en memoria: la sesión
          // va en el JWT y el catálogo en Redis. Pegar cada visitante a una instancia
          // estropearía justo lo que la sección 5 quiere demostrar, porque las instancias
          // nuevas del autoescalado se quedarían sin tráfico que atender.
          requestTimeout: 60
          pickHostNameFromBackendAddress: true
          probe: {
            id: '${idGateway}/probes/sonda-salud'
          }
        }
      }
    ]
    httpListeners: [
      {
        name: 'escucha-80'
        properties: {
          frontendIPConfiguration: {
            id: '${idGateway}/frontendIPConfigurations/frontal-publico'
          }
          frontendPort: {
            id: '${idGateway}/frontendPorts/puerto-80'
          }
          protocol: 'Http'
        }
      }
    ]
    requestRoutingRules: [
      {
        name: 'regla-api'
        properties: {
          ruleType: 'Basic'
          // OBLIGATORIA desde la versión 2021-08-01 de la API. Sin `priority` el despliegue
          // falla con un mensaje que no dice cuál es el campo que falta.
          priority: 100
          httpListener: {
            id: '${idGateway}/httpListeners/escucha-80'
          }
          backendAddressPool: {
            id: '${idGateway}/backendAddressPools/grupo-api'
          }
          backendHttpSettings: {
            id: '${idGateway}/backendHttpSettingsCollection/ajustes-api'
          }
        }
      }
    ]
  }
}

output ipGateway string = ipPublica.properties.ipAddress
output urlGateway string = 'http://${ipPublica.properties.dnsSettings.fqdn}'
output nombreGateway string = gateway.name
output nombrePoliticaWaf string = politicaWaf.name
