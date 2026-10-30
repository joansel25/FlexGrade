
@description('Región.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Etiquetas comunes de la sección 12.2. Las arma `modules/comun/etiquetas.bicep`.')
param tags object

@description('Subred delegada a Container Instances.')
param subredTareasId string

@description('Servidor de inicio de sesión del ACR.')
param acrLoginServer string

@description('Etiqueta de la imagen. La misma que ejecuta la aplicación: las migraciones tienen que corresponder con el código desplegado.')
param etiquetaImagen string

@description('Identificador de la identidad asignada por el usuario, que ya tiene permiso de descarga sobre el ACR.')
param identidadId string

@description('Cadena de conexión a PostgreSQL. Llega del Key Vault y no se escribe en ningún sitio.')
@secure()
param databaseUrl string

@description('Si además de migrar hay que sembrar datos de ejemplo. En un ambiente real esto va en false.')
param sembrarDatos bool = true

// `alembic upgrade head` siempre; el seed solo si se pide. Van encadenados con `&&` para que un
// fallo de la migración impida sembrar sobre un esquema a medias.
var comando = sembrarDatos
  ? 'alembic upgrade head && python -m app.infrastructure.seed'
  : 'alembic upgrade head'

resource tarea 'Microsoft.ContainerInstance/containerGroups@2023-05-01' = {
  name: '${prefijo}-migraciones'
  location: ubicacion
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identidadId}': {}
    }
  }
  properties: {
    osType: 'Linux'
    // Nunca se reinicia: es una tarea, no un servicio. Si se reiniciara, volvería a sembrar en
    // bucle —el seed es idempotente, así que no rompería nada, pero tampoco terminaría—.
    restartPolicy: 'Never'
    subnetIds: [{ id: subredTareasId }]
    imageRegistryCredentials: [
      {
        server: acrLoginServer
        identity: identidadId
      }
    ]
    containers: [
      {
        name: 'migraciones'
        properties: {
          image: '${acrLoginServer}/matricula-backend:${etiquetaImagen}'
          command: ['/bin/sh', '-c', comando]
          environmentVariables: [
            {
              name: 'DATABASE_URL'
              secureValue: databaseUrl
            }
            // `Settings` exige las tres, aunque las migraciones solo usen la primera: la
            // aplicación no arranca sin ellas y `alembic/env.py` importa la configuración. Se
            // rellenan con valores inertes en vez de sacarlos del Key Vault, porque este
            // contenedor no necesita ni Redis ni firmar tokens.
            {
              name: 'REDIS_URL'
              value: 'redis://localhost:6379/0'
            }
            {
              // `value` y no `secureValue`, aunque el nombre asuste: esto NO es un secreto, es
              // un relleno para que `Settings` valide. Marcarlo como secreto mentiría sobre lo
              // que es, y escondería en los registros un valor que conviene ver de un vistazo
              // para confirmar que nadie firmó nada con él.
              name: 'JWT_SECRET'
              value: 'relleno-las-migraciones-no-firman-tokens'
            }
          ]
          resources: {
            requests: {
              // Lo mínimo que admite Container Instances. La tarea dura menos de un minuto.
              cpu: 1
              memoryInGB: 1
            }
          }
        }
      }
    ]
  }
}

output nombreTarea string = tarea.name
output estado string = tarea.properties.provisioningState
