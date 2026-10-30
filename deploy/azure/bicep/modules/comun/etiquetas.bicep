// Las etiquetas comunes de la sección 12.2, declaradas UNA sola vez.
//
// No crea recursos: exporta un tipo, una lista y una función que importan las plantillas de
// entrada (`import { etiquetas } from 'modules/comun/etiquetas.bicep'`). Así las cuatro
// etiquetas obligatorias no pueden escribirse distinto en dos sitios, que es justo lo que la
// política de gobernanza castigaría.

@export()
@description('Valores válidos de la etiqueta `Ambiente`. NO es el ambiente de la aplicación (`ENVIRONMENT`): con `dev`, el backend escribe los logs en texto plano y Log Analytics deja de poder leerlos.')
type ambienteEtiqueta = 'dev' | 'demo' | 'compartido'

@export()
@description('La misma lista que `ambienteEtiqueta`, como valor. La consume la regla de gobernanza que audita los valores válidos; las pruebas comprueban que las dos coinciden.')
var ambientesValidos = ['dev', 'demo', 'compartido']

@export()
@description('Las cuatro etiquetas obligatorias, más `Vigencia` solo cuando se pasa: es una fecha de revisión que solo tiene sentido en lo efímero. La clave es `Dueno`, sin eñe (12.2).')
func etiquetas(ambiente ambienteEtiqueta, dueno string, centroCosto string, vigencia string) object =>
  union(
    {
      Proyecto: 'FlexGrade'
      Dueno: dueno
      Ambiente: ambiente
      CentroCosto: centroCosto
    },
    empty(vigencia) ? {} : { Vigencia: vigencia }
  )
