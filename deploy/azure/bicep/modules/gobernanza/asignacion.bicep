// Aplica la iniciativa de gobernanza sobre la suscripción, en modo auditoría o en modo bloqueo.
//
// AUDITAR ANTES DE BLOQUEAR (13.3). El orden es obligatorio:
//
//   1. `audit`: todo se evalúa y nada se rechaza. Se inventarían los incumplimientos.
//   2. Se corrigen EN EL BICEP, nunca con Modify ni DeployIfNotExists.
//   3. Se levanta la demo entera en `audit` y se comprueba que no queda nada incumplido.
//   4. Solo entonces `enforce`. Recordar que Deny frena lo nuevo, pero no repara lo existente.
//
// Un único parámetro mueve las dos palancas a la vez: el EFECTO de las reglas que lo admiten
// (Audit → Deny) y el `enforcementMode` de la asignación, que es lo único que frena a «Require a
// tag», cuyo efecto es Deny fijo. Con `DoNotEnforce` Azure sigue evaluando y mostrando el
// cumplimiento, pero no rechaza nada.

targetScope = 'subscription'

@description('`audit` evalúa sin rechazar; `enforce` bloquea. Lo decide Seguridad tras validar (13.3).')
@allowed(['audit', 'enforce'])
param modo string

@description('Identificador de la iniciativa.')
param iniciativaId string

@description('Grupos que quedan FUERA de la gobernanza, por nombre.')
param gruposExcluidos string[]

var bloquear = modo == 'enforce'

resource asignacion 'Microsoft.Authorization/policyAssignments@2024-04-01' = {
  name: 'flexgrade-gobernanza'
  properties: {
    displayName: 'FlexGrade: gobernanza (${modo})'
    policyDefinitionId: iniciativaId
    enforcementMode: bloquear ? 'Default' : 'DoNotEnforce'
    // `NetworkWatcherRG` lo crea Azure por su cuenta y sin etiquetas. Con la regla de etiquetas
    // en Deny, Azure dejaría de poder crearlo y la red perdería su supervisión sin un aviso claro.
    notScopes: [for grupo in gruposExcluidos: '${subscription().id}/resourceGroups/${grupo}']
    parameters: {
      efecto: {
        value: bloquear ? 'Deny' : 'Audit'
      }
    }
    nonComplianceMessages: [
      {
        message: 'FlexGrade: el recurso incumple la gobernanza de 13.3. Revisa las etiquetas (Proyecto, Dueno, Ambiente, CentroCosto) y que PostgreSQL siga sin acceso público.'
      }
    ]
  }
}

output id string = asignacion.id
output modo string = modo
