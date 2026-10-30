// Los roles integrados que usa el proyecto y los grupos de Entra a los que se asignan.
//
// Los GUID se resolvieron con `az role definition list --name "<rol>" --query "[0].name"` el
// 2026-10-29, como exige el documento: nunca de memoria. Son fijos en todo Azure.

@export()
var roles = {
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  contributor: 'b24988ac-6180-42a0-ab88-20f7382dd24c'
  costManagementContributor: '434105ed-43f6-45c7-a02f-909b2ba83430'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  logAnalyticsReader: '73c42c96-874c-492b-b04d-ab87d138a893'
  monitoringContributor: '749f88d5-cbae-40b8-bcfc-e573ddc772fa'
  rbacAdministrator: 'f58310d9-a9f6-439a-9e8d-f62e7b41a168'
  resourcePolicyContributor: '36243c78-bf99-498c-9df9-86d9f8d28608'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  websiteContributor: 'de139f84-1756-47ae-9be6-808fbbe84772'
}

@export()
@description('''
  Identificadores de objeto de los cinco grupos de Entra ID de la sección 10.1.

  UN VALOR VACÍO SIGNIFICA «SIN ASIGNAR», y es el estado actual: la cuenta del proyecto no puede
  crear grupos en el directorio de la universidad (`allowedToCreateSecurityGroups = false`). Cada
  asignación se condiciona a que su grupo tenga valor, así que el código queda listo y se activa
  solo cuando TI cree los grupos. Es la excepción registrada en INFRASTRUCTURE §7.
''')
type gruposEntra = {
  infraestructura: string
  desarrollo: string
  seguridad: string
  monitoreo: string
  finops: string
}
