// El presupuesto mensual de la sección 12.3, sobre la suscripción (dedicada a FlexGrade).
//
// UN PRESUPUESTO AVISA, NO DETIENE. No se le asocia ninguna acción que apague o borre recursos:
// borrar por un umbral de coste es una forma de perder datos que nadie decidió perder (12.3).
// Lo que de verdad detiene el gasto en este proyecto es `scripts/destruir.sh`.

targetScope = 'subscription'

@description('Monto mensual, en la moneda de facturación de la suscripción. Sin valor por defecto: lo fija FinOps con el saldo disponible (12.3, 14).')
@minValue(1)
param monto int

@description('Primer día del mes en que empieza a contar, con formato AAAA-MM-01.')
@minLength(10)
@maxLength(10)
param inicio string

@description('Correos que reciben los avisos. Sin valor por defecto (14).')
@minLength(1)
param correos string[]

@description('Grupo de acciones que también recibe los avisos.')
param grupoAccionesId string

// Los tres avisos de 12.3. El previsto al 100 % es el que da margen: avisa cuando, al ritmo
// actual, el mes va a acabar por encima, antes de que el gasto ocurra.
var avisos = {
  consumoReal80: {
    umbral: 80
    tipo: 'Actual'
  }
  prevision100: {
    umbral: 100
    tipo: 'Forecasted'
  }
  consumoReal100: {
    umbral: 100
    tipo: 'Actual'
  }
}

resource presupuesto 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: 'flexgrade-presupuesto-mensual'
  properties: {
    category: 'Cost'
    amount: monto
    timeGrain: 'Monthly'
    timePeriod: {
      startDate: inicio
    }
    notifications: toObject(
      items(avisos),
      a => a.key,
      a => {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: a.value.umbral
        thresholdType: a.value.tipo
        contactEmails: correos
        contactGroups: [grupoAccionesId]
      }
    )
  }
}
