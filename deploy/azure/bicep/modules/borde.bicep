/*
  El borde: Application Gateway con WAF, y el almacenamiento del frontend.

  Es la sección 2 de `INFRASTRUCTURE.md` —«Application Gateway (WAF)»— y la sección 4, que fija
  el puerto 80 de cara a internet.

  ES LA LÍNEA MÁS CARA DE TODA LA INFRAESTRUCTURA

  WAF_v2 cuesta 0,443 USD/hora de coste fijo más 0,0144 por unidad de capacidad: unos 0,46
  USD/hora, casi cuatro veces el perfil económico entero. No admite apagarse ni bajar a cero, y
  no existe un nivel más barato con WAF. Por eso este módulo es OPCIONAL: se despliega solo con
  `desplegarBorde: true`, que va en el perfil de demostración y no en el económico.

  Aquí NO hay Front Door, y es a propósito. El único nivel que trae WAF gestionado es Premium,
  con 330 USD/mes de tarifa base —confirmado contra la API de precios—, y además Front Door no
  aparece en ninguna parte de `INFRASTRUCTURE.md`. Se quedó en la lista de tecnologías por
  arrastre.

  EL PUERTO 8000 DEL DOCUMENTO NO EXISTE DE CARA AL GATEWAY

  La sección 4 pide «App Gateway -> App: 8000». Ese es el puerto en el que uvicorn escucha DENTRO
  del contenedor, y App Service no lo publica: termina TLS por su cuenta y solo expone 443. El
  gateway habla con el backend por HTTPS al 443, y quien traduce al 8000 es el propio App
  Service con `WEBSITES_PORT`. Es la misma regla del documento, cumplida donde de verdad ocurre.

  `pickHostNameFromBackendAddress` es imprescindible: App Service decide qué sitio sirve MIRANDO
  LA CABECERA `Host`. Si el gateway reenviara la del visitante, App Service no reconocería el
  nombre y devolvería su página de error genérica en lugar de la aplicación — un 404 que no
  menciona en ningún momento que la culpa es de una cabecera.

  LO QUE ESTE MÓDULO NO CIERRA

  El App Service SIGUE siendo alcanzable por su URL `azurewebsites.net`, así que se puede
  esquivar el WAF yendo directo. Cerrarlo es una restricción de acceso por dirección de origen
  en el sitio, y se deja fuera a propósito: durante la sustentación conviene poder comparar la
  respuesta con y sin WAF delante. En un ambiente real sería lo primero que habría que añadir.
*/

@description('Región.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Sufijo único global: el nombre de la cuenta de almacenamiento se publica en un dominio público.')
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

var idGateway = resourceId('Microsoft.Network/applicationGateways', '${prefijo}-gateway')

resource gateway 'Microsoft.Network/applicationGateways@2023-09-01' = {
  name: '${prefijo}-gateway'
  location: ubicacion
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

// ---------------------------------------------------------------------------
// El frontend
// ---------------------------------------------------------------------------
//
// La SPA es HTML, CSS y JavaScript ya compilados: no necesita servidor. Una cuenta de
// almacenamiento con sitio estático cuesta céntimos al mes frente a los 0,095 USD/hora de un
// App Service que solo devolvería archivos.
//
// OJO: activar el sitio estático NO SE PUEDE HACER DESDE BICEP. Es una propiedad del plano de
// datos, no de ARM, así que este módulo crea la cuenta y el paso que la activa y sube el
// `dist/` va en el script de arranque:
//
//   az storage blob service-properties update --account-name <cuenta> \
//     --static-website --index-document index.html --404-document index.html
//   az storage blob upload-batch --account-name <cuenta> -s frontend/dist -d '$web'
//
// El documento 404 apunta también a `index.html` porque React Router resuelve las rutas en el
// navegador: sin eso, recargar la página estando en `/matricula` da un 404 de almacenamiento.

resource almacenamientoWeb 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${prefijo}web${sufijo}'
  location: ubicacion
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    // El contenido del sitio estático es público POR DEFINICIÓN: son los archivos que el
    // navegador de cualquiera descarga. No hay nada que proteger aquí, y desactivarlo impediría
    // que el sitio sirviera.
    allowBlobPublicAccess: true
  }
}

output ipGateway string = ipPublica.properties.ipAddress
output urlGateway string = 'http://${ipPublica.properties.dnsSettings.fqdn}'
output nombreGateway string = gateway.name
output nombrePoliticaWaf string = politicaWaf.name
output cuentaAlmacenamientoWeb string = almacenamientoWeb.name
// La devuelve el propio recurso. Componerla a mano NO funciona: lleva un número de zona
// (`z19`, `z22`...) que depende de dónde caiga la cuenta y que no se puede saber de antemano.
output urlFrontend string = almacenamientoWeb.properties.primaryEndpoints.web
