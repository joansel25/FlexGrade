// Los nombres de los recursos, calculados en UN solo sitio.
//
// POR QUÉ HACE FALTA
//
// Las alertas viven en el grupo persistente y vigilan recursos del grupo efímero por su
// `_ResourceId`. No pueden leer las salidas de un despliegue que todavía no existe —la demo se
// levanta después, y se destruye—, y escribir el identificador a mano lo dejaría desactualizado el
// día que alguien cambie un nombre. Con esta función, `main.bicep` crea el recurso y `base.bicep`
// lo vigila con el MISMO cálculo.
//
// FUNCIONA PORQUE LOS NOMBRES SON DETERMINISTAS. El sufijo es `uniqueString` del identificador del
// grupo: mismo grupo, mismo sufijo, sesión tras sesión. `idGrupo` reproduce el formato exacto de
// `resourceGroup().id` para que un grupo pueda calcular el sufijo del otro.

@export()
@description('Sufijo único global de seis caracteres, derivado del identificador del grupo.')
func sufijo(idGrupo string) string => take(uniqueString(idGrupo), 6)

@export()
@description('El identificador de un grupo con el formato exacto de `resourceGroup().id`. Recibe `subscription().id`, que una función no puede consultar por su cuenta.')
func idGrupo(idSuscripcion string, nombreGrupo string) string => '${idSuscripcion}/resourceGroups/${nombreGrupo}'

@export()
@description('Nombres de los recursos del grupo EFÍMERO que algo de fuera necesita encontrar.')
func nombresEfimeros(prefijo string, sufijo string) object => {
  plan: '${prefijo}-plan'
  app: '${prefijo}-api-${sufijo}'
  gateway: '${prefijo}-gateway'
  postgres: '${prefijo}-pg-${sufijo}'
  redis: '${prefijo}-redis-${sufijo}'
}

@export()
@description('Nombres de los recursos del grupo PERSISTENTE.')
func nombresBase(prefijo string, sufijo string) object => {
  // El nombre del ACR solo admite letras y números: sin guiones, al contrario que el resto.
  acr: '${prefijo}acr${sufijo}'
  keyVault: '${prefijo}-kv-${sufijo}'
  registros: '${prefijo}-logs-${sufijo}'
  appInsights: '${prefijo}-appinsights-${sufijo}'
  grupoAcciones: '${prefijo}-alertas'
}
