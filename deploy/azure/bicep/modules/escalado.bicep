/*
  Autoescalado del plan de App Service: la sección 5 de `INFRASTRUCTURE.md`.

  DOS COSAS DEL DOCUMENTO NO SE PUEDEN CUMPLIR TAL CUAL, Y HAY QUE SABERLO

  1. «App Service Plan: SKU B1 con autoescalado» es una contradicción. El nivel Basic NO admite
     autoescalado: la regla se crea y nunca dispara. El autoescalado empieza en Standard, de ahí
     que `skuAppService` sea `S1` en el perfil de demostración. Cuesta 0,095 USD/hora por
     instancia frente a 0,018 del B1.

  2. «Pico matrícula: min 6, max 12» tampoco. El nivel Standard llega a DIEZ instancias, no a
     doce; pasar de ahí exige Premium v3. El máximo queda en 10 y se deja dicho, porque un
     `maximum: 12` que Azure recorta en silencio es peor que un 10 explícito.

  POR QUÉ HAY TRES PERFILES Y NO DOS

  Un perfil con `recurrence` dice cuándo EMPIEZA, nunca cuándo termina: se queda aplicado hasta
  que otro perfil recurrente lo reemplaza. Con solo «normal» + «pico», el pico arranca el lunes
  a las 7 y ya no se va nunca — seis instancias mínimas ardiendo un domingo a las tres de la
  mañana, que sobre un crédito de estudiante se nota en dos días.

  El tercer perfil, `fin-del-pico`, es el que devuelve las capacidades normales. Es el mismo
  apareamiento que hace el portal por debajo cuando se define un horario desde la interfaz.

  LAS REGLAS REACTIVAS VAN EN LOS TRES

  Un perfil de autoescalado no hereda nada del anterior. Si las reglas de CPU estuvieran solo en
  el perfil normal, durante la ventana de matrícula —justo cuando hacen falta— el sistema se
  quedaría clavado en seis instancias pasara lo que pasara con la carga.
*/

@description('Región.')
param ubicacion string

@description('Prefijo de los nombres.')
param prefijo string

@description('Identificador del plan de App Service al que se le aplica el autoescalado.')
param planId string

@description('Nombre del plan. Solo se usa para que la salida sea legible.')
param planNombre string

@description('Instancias mínimas fuera de la ventana de matrícula.')
@minValue(1)
param minimoNormal int = 1

@description('Instancias máximas fuera de la ventana de matrícula.')
@minValue(1)
param maximoNormal int = 2

@description('Instancias mínimas durante la ventana de matrícula.')
@minValue(1)
param minimoPico int = 6

@description('Instancias máximas durante la ventana de matrícula. El nivel Standard NO pasa de 10.')
@minValue(1)
@maxValue(10)
param maximoPico int = 10

@description('Días de la semana en que se abre la matrícula.')
param diasDePico array = [
  'Monday'
  'Tuesday'
  'Wednesday'
  'Thursday'
  'Friday'
]

@description('Hora a la que arranca la ventana de matrícula, hora de Colombia.')
@minValue(0)
@maxValue(23)
param horaInicioPico int = 7

@description('Hora a la que se cierra la ventana y las capacidades vuelven a las normales.')
@minValue(0)
@maxValue(23)
param horaFinPico int = 22

@description('Aplica las capacidades del PICO como perfil por defecto, ignorando el horario. Existe para poder sustentar: esperar a que sean las siete de un martes no es una opción, y con el perfil normal (máximo 2) lo único que se ve es un salto de 1 a 2 instancias. CUESTA DINERO: seis instancias S1 son 0,57 USD/hora solo de App Service.')
param modoDemostracion bool = false

// Hora de Colombia. Azure NO acepta `America/Bogota`: usa los nombres de zona de Windows, y el
// que corresponde es este. Con un nombre que no reconoce, el despliegue falla.
var zonaHoraria = 'SA Pacific Standard Time'

// ---------------------------------------------------------------------------
// Las reglas reactivas
// ---------------------------------------------------------------------------
//
// «+1 si CPU > 70% por 5 min; -1 si CPU < 30% por 10 min», literal del documento.
//
// LA ASIMETRÍA ENTRE LAS DOS VENTANAS ES DELIBERADA y viene del propio documento: subir tarda 5
// minutos en decidirse y bajar 10. Se sube rápido porque la alternativa es que el estudiante
// vea un error; se baja despacio porque una bajada apresurada durante una meseta de carga
// devuelve el sistema al punto de saturación y arranca un vaivén de subidas y bajadas.
//
// El `cooldown` refuerza lo mismo: tras una escalada, la instancia nueva tarda en arrancar el
// contenedor y en recibir tráfico. Sin espera, la CPU seguiría alta —todavía no se ha repartido
// nada— y el autoescalado pediría una tercera instancia que tampoco hacía falta.

var reglaSubir = {
  metricTrigger: {
    metricName: 'CpuPercentage'
    metricResourceUri: planId
    timeGrain: 'PT1M'
    statistic: 'Average'
    timeWindow: 'PT5M'
    timeAggregation: 'Average'
    operator: 'GreaterThan'
    threshold: 70
    dimensions: []
    // Mira la CPU del CONJUNTO, no la de cada instancia por separado. Con `true`, una sola
    // instancia ocupada dispararía una escalada que el conjunto no necesita.
    dividePerInstance: false
  }
  scaleAction: {
    direction: 'Increase'
    type: 'ChangeCount'
    value: '1'
    cooldown: 'PT5M'
  }
}

var reglaBajar = {
  metricTrigger: {
    metricName: 'CpuPercentage'
    metricResourceUri: planId
    timeGrain: 'PT1M'
    statistic: 'Average'
    timeWindow: 'PT10M'
    timeAggregation: 'Average'
    operator: 'LessThan'
    threshold: 30
    dimensions: []
    dividePerInstance: false
  }
  scaleAction: {
    direction: 'Decrease'
    type: 'ChangeCount'
    value: '1'
    cooldown: 'PT10M'
  }
}

var reglas = [reglaSubir, reglaBajar]

var capacidadNormal = {
  minimum: string(minimoNormal)
  maximum: string(maximoNormal)
  default: string(minimoNormal)
}

var capacidadPico = {
  minimum: string(minimoPico)
  maximum: string(maximoPico)
  default: string(minimoPico)
}

// El perfil por defecto: el que rige cuando ningún horario está activo.
var perfilPorDefecto = {
  name: modoDemostracion ? 'demostracion-pico-permanente' : 'normal'
  capacity: modoDemostracion ? capacidadPico : capacidadNormal
  rules: reglas
}

// En modo demostración los perfiles con horario SOBRAN, y además estorban: a las 22:00 el
// `fin-del-pico` bajaría el mínimo a 1 en mitad de la sustentación.
var perfilesConHorario = modoDemostracion ? [] : [
  {
    name: 'pico-matricula'
    capacity: capacidadPico
    rules: reglas
    recurrence: {
      frequency: 'Week'
      schedule: {
        timeZone: zonaHoraria
        days: diasDePico
        hours: [horaInicioPico]
        minutes: [0]
      }
    }
  }
  {
    name: 'fin-del-pico'
    capacity: capacidadNormal
    rules: reglas
    recurrence: {
      frequency: 'Week'
      schedule: {
        timeZone: zonaHoraria
        days: diasDePico
        hours: [horaFinPico]
        minutes: [0]
      }
    }
  }
]

resource autoescalado 'Microsoft.Insights/autoscalesettings@2022-10-01' = {
  name: '${prefijo}-autoescalado'
  location: ubicacion
  properties: {
    name: '${prefijo}-autoescalado'
    targetResourceUri: planId
    enabled: true
    profiles: concat([perfilPorDefecto], perfilesConHorario)
    // Sin notificaciones por correo: no hay buzón de operación en un proyecto académico, y una
    // dirección inventada hace que cada escalada genere un rebote.
    notifications: []
  }
}

output nombreRegla string = autoescalado.name
output planVigilado string = planNombre
output modoDemostracionActivo bool = modoDemostracion
