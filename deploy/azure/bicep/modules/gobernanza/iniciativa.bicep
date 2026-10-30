// La iniciativa de Azure Policy de FlexGrade: las cinco reglas de la sección 13.3.
//
// SOLO DEFINE; NO APLICA NADA. Dónde se aplica y en qué modo lo decide `asignacion.bicep`, así
// que pasar de auditar a bloquear (13.3) no exige tocar ninguna definición.
//
// Los identificadores de las integradas se resolvieron con `az policy definition list` el
// 2026-10-29, como exige el documento: nunca de memoria.
//
// SIN `Modify` NI `DeployIfNotExists` (13.3): la remediación se hace corrigiendo el Bicep, no
// dejando que Azure cambie recursos por su cuenta. Por eso la iniciativa no necesita identidad.

targetScope = 'subscription'

import { ambientesValidos } from '../comun/etiquetas.bicep'

var integradas = {
  postgresSinAccesoPublico: '5e1de0e3-42cb-4ebc-a86d-61d0c619ca48'
  etiquetaEnRecursos: '871b6d14-10aa-478d-b590-94f262ecfa99'
  etiquetaEnGrupos: '96670d01-0a4d-4649-9c89-2d3abc0a5025'
  appServiceSoloHttps: 'a4af4a39-4135-47fb-b175-47fbdf85311d'
  postgresSslObligatorio: 'c29c38cb-74a7-4505-9a06-e588ab86620a'
  logsDeKeyVault: 'cf820ca0-f99e-4f3e-84fb-66e913812d21'
  logsDeAppService: '91a78b24-f231-4a8a-8da9-02c35b2b6510'
}

var etiquetasObligatorias = [
  'Proyecto'
  'Dueno'
  'Ambiente'
  'CentroCosto'
]

func integrada(id string) string => tenantResourceId('Microsoft.Authorization/policyDefinitions', id)

// ---------------------------------------------------------------------------
// La regla personalizada: valores de etiqueta válidos (13.3)
// ---------------------------------------------------------------------------
//
// Las integradas comprueban que la etiqueta EXISTE, no qué dice. Esta cierra el hueco: un
// `Ambiente: produccion` o un `Dueno` vacío pasarían la otra sin que nadie lo viera.
//
// Modo `Indexed`: solo evalúa lo que admite etiquetas. En `All` marcaría como incumplidos
// recursos que no pueden llevarlas.

resource valoresDeEtiquetas 'Microsoft.Authorization/policyDefinitions@2023-04-01' = {
  name: 'flexgrade-valores-de-etiquetas'
  properties: {
    displayName: 'FlexGrade: valores de etiqueta válidos'
    description: '`Ambiente` debe ser dev, demo o compartido, y `Dueno` y `CentroCosto` no pueden ir vacíos (13.3).'
    policyType: 'Custom'
    mode: 'Indexed'
    metadata: {
      category: 'Tags'
    }
    parameters: {
      efecto: {
        type: 'String'
        allowedValues: ['Audit', 'Deny']
        defaultValue: 'Audit'
      }
    }
    policyRule: {
      if: {
        anyOf: [
          {
            field: 'tags[\'Ambiente\']'
            notIn: ambientesValidos
          }
          {
            field: 'tags[\'Dueno\']'
            equals: ''
          }
          {
            field: 'tags[\'CentroCosto\']'
            equals: ''
          }
        ]
      }
      then: {
        effect: '[parameters(\'efecto\')]'
      }
    }
  }
}

// ---------------------------------------------------------------------------
// La iniciativa
// ---------------------------------------------------------------------------

// Una referencia por etiqueta y por destino: la integrada recibe UN nombre de etiqueta.
var referenciasPorEtiqueta = [
  for etiqueta in etiquetasObligatorias: [
    {
      policyDefinitionReferenceId: 'etiqueta-en-recursos-${etiqueta}'
      policyDefinitionId: integrada(integradas.etiquetaEnRecursos)
      parameters: {
        tagName: { value: etiqueta }
      }
    }
    {
      policyDefinitionReferenceId: 'etiqueta-en-grupos-${etiqueta}'
      policyDefinitionId: integrada(integradas.etiquetaEnGrupos)
      parameters: {
        tagName: { value: etiqueta }
      }
    }
  ]
]

var referenciasDeEtiquetas = flatten(referenciasPorEtiqueta)

var referenciasFijas = [
  {
    // Ya se cumple: PostgreSQL vive inyectado en una subred delegada, sin acceso público. Esta
    // regla impide que alguien lo abra después desde el portal.
    policyDefinitionReferenceId: 'postgres-sin-acceso-publico'
    policyDefinitionId: integrada(integradas.postgresSinAccesoPublico)
    parameters: {
      effect: { value: '[parameters(\'efecto\')]' }
    }
  }
  {
    policyDefinitionReferenceId: 'valores-de-etiquetas'
    policyDefinitionId: valoresDeEtiquetas.id
    parameters: {
      efecto: { value: '[parameters(\'efecto\')]' }
    }
  }
  {
    // Siempre en Audit, también en modo «enforce» (13.3): `httpsOnly` ya lo fija el Bicep, y
    // este aviso existe para detectar si alguien lo cambia a mano.
    policyDefinitionReferenceId: 'app-service-solo-https'
    policyDefinitionId: integrada(integradas.appServiceSoloHttps)
    parameters: {
      effect: { value: 'Audit' }
    }
  }
  {
    // La cobertura de transporte seguro para PostgreSQL Flexible que 13.3 pedía «si existe».
    // Existe, y comprueba `require_secure_transport`, que fija `datos/postgres.bicep`.
    policyDefinitionReferenceId: 'postgres-ssl-obligatorio'
    policyDefinitionId: integrada(integradas.postgresSslObligatorio)
  }
  {
    // Cumple aunque la retención del workspace sea de 30 días y la regla pida 365: la regla da
    // por buena cualquier exportación que no vaya a una cuenta de almacenamiento, y la nuestra va
    // a Log Analytics. Comprobado leyendo su `existenceCondition`.
    policyDefinitionReferenceId: 'logs-de-key-vault'
    policyDefinitionId: integrada(integradas.logsDeKeyVault)
  }
  {
    policyDefinitionReferenceId: 'logs-de-app-service'
    policyDefinitionId: integrada(integradas.logsDeAppService)
  }
]

resource iniciativa 'Microsoft.Authorization/policySetDefinitions@2023-04-01' = {
  name: 'flexgrade-gobernanza'
  properties: {
    displayName: 'FlexGrade: gobernanza (13.3)'
    description: 'Base de datos privada, etiquetas obligatorias y válidas, transporte seguro y registros de diagnóstico.'
    policyType: 'Custom'
    metadata: {
      category: 'FlexGrade'
    }
    parameters: {
      efecto: {
        type: 'String'
        allowedValues: ['Audit', 'Deny']
        defaultValue: 'Audit'
      }
    }
    policyDefinitions: concat(referenciasFijas, referenciasDeEtiquetas)
  }
}

output iniciativaId string = iniciativa.id
output reglas int = length(concat(referenciasFijas, referenciasDeEtiquetas))
