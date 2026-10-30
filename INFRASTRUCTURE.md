INFRASTRUCTURE.md

1. Plataforma y modelo
   - Proveedor: Microsoft Azure (cuenta estudiantil, creditos limitados)
   - Modelo: PaaS
   - IaC: Bicep

2. Inventario de recursos (lo que el Bicep debe crear)
   - App Service Plan: SKU B1 (1 vCPU, 1.75 GB) con autoescalado
   - Azure Database for PostgreSQL Flexible Server: B1ms + standby
   - Azure Cache for Redis: Basic C0
   - Application Gateway (WAF)
   - VNet + NAT Gateway

3. Topologia de red
   - VNet 10.0.0.0/16
   - Subred publica 10.0.1.0/24 (Application Gateway)
   - Subred app privada 10.0.2.0/24 (App Service)
   - Subred datos privada (PostgreSQL primaria + Redis)
   - Subred respaldo privada (PostgreSQL standby)

4. Reglas de firewall (puertos)
   - Internet -> App Gateway: 80
   - App Gateway -> App: 8000
   - App -> PostgreSQL: 5432
   - App -> Redis: 6379

5. Autoescalado
   - Normal: min 1, max 2
   - Pico matricula (por horario): min 6, max 12
   - Reactivo: +1 instancia si CPU > 70% por 5 min; -1 si CPU < 30% por 10 min

6. Restriccion de costos
   - Cuenta estudiantil: usar SKUs mas economicos (B1, B1ms, C0)
   - Apagar/reducir a minimos fuera de ventanas de prueba

---

7. Lo que se implemento, y donde difiere

   Las secciones 1-6 son el requisito tal y como lo pide el documento de la Fase I, y se dejan
   escritas como estan. Esta seccion anota lo que la plataforma no permitio cumplir literalmente.
   Casi ninguna es una renuncia: en la mayoria el requisito se cumple por una via distinta a la
   prevista. Las excepciones son 7.8, donde si se decide no implementar lo que el documento
   describe, y 7.10, donde lo implementado no se puede activar todavia; las dos quedan
   explicadas.

   7.1 SKU B1 con autoescalado -> S1
       El nivel Basic NO admite autoescalado. Azure acepta la regla, la muestra en el portal y
       nunca dispara. S1 tiene el mismo vCPU y la misma RAM (1 vCPU, 1,75 GB); lo que cambia es
       el nivel, que es lo unico que desbloquea el autoescalado. Cuesta 0,095 USD/hora por
       instancia frente a 0,018.

       `main.bicep` exige `skuAppService == 'S1'` para desplegar siquiera la regla: una regla
       muerta que aparenta funcionar es peor que no tenerla.

   7.2 Pico min 6 / max 12 -> min 6 / max 10
       El nivel Standard llega a DIEZ instancias. Pasar de ahi exige Premium v3. El minimo de 6
       si se respeta. Un `maximum: 12` que Azure recorta en silencio engaña mas que ayuda.

   7.3 PostgreSQL B1ms + standby -> D2ds_v4 (General Purpose) + standby
       El nivel Burstable no admite replica en espera. Es la misma contradiccion que el B1.

       CONSECUENCIA DE COSTE, y no es menor: el B1ms entra en la capa GRATUITA de Flexible Server
       (750 h/mes durante 12 meses) y el D2ds_v4 no. En la facturacion real de septiembre
       PostgreSQL costo 0,00 USD con el perfil economico; con el de demostracion son ~0,40
       USD/hora entre primaria y replica.

       Por eso hay dos perfiles: el economico usa B1ms sin replica —gratis, para probar que el
       software funciona— y el de demostracion usa D2ds_v4 con replica, que es el que cumple el
       requisito de alta disponibilidad.

   7.4 App Gateway -> App: 8000 -> 443
       El 8000 es el puerto en el que uvicorn escucha DENTRO del contenedor. App Service no lo
       publica: termina TLS por su cuenta y solo expone el 443. El gateway habla con el backend
       por HTTPS al 443, y quien traduce al 8000 es el propio App Service con `WEBSITES_PORT`.

       La tabla de puertos real, en cuatro saltos en vez de dos:

           Internet     -> App Gateway:   80
           App Gateway  -> App Service:   443 (HTTPS)
           App Service  -> contenedor:    8000 (uvicorn, via WEBSITES_PORT)
           App          -> PostgreSQL:    5432
           App          -> Redis:         10000 (TLS)

   7.5 Azure Cache for Redis Basic C0 -> Azure Managed Redis Balanced B0
       El producto esta RETIRADO: crear uno falla pidiendo «create Azure Managed Redis instance
       instead». No fue una eleccion.

       Y salio mas CARO, no mas barato: la tarifa publicada de 0,018 USD/hora es POR NODO y el
       nivel Balanced despliega DOS para poder dar alta disponibilidad. Son 0,036 reales frente a
       los 0,022 del C0 — un 64% mas. A cambio trae replica y SLA, que el C0 no tenia. No existe
       un nivel de un solo nodo.

       Obliga ademas a TLS por el puerto 10000, de ahi el cambio en 7.4.

   7.6 El NAT Gateway es opcional
       La seccion 3 lo pide y se despliega en el perfil de demostracion. En el economico va
       apagado: en la facturacion real fue el 37% del gasto —5,14 USD de 14,02— mas que Redis y
       mas que el App Service, y el sistema no lo necesita para funcionar. App Service ya publica
       un conjunto estable de direcciones de salida, y PostgreSQL y Redis se alcanzan por red
       privada.

   7.7 Front Door no se despliega
       No aparece en las secciones 1-6; venia arrastrado de la lista de tecnologias del proyecto.
       Se evaluo igualmente: el unico nivel con WAF gestionado es Premium, con 330 USD/mes de
       tarifa base verificada contra la API de precios (Standard son 35, pero no incluye WAF).
       Frente a un credito de 100 USD, descartado. La funcion de WAF la cubre Application Gateway
       WAF_v2 a 0,443 USD/hora, que ademas permite el modelo de infraestructura efimera.

   7.8 La autenticacion de usuarios NO usa Microsoft Entra External ID
       El documento de la Fase I lo nombra como el servicio que autentica a estudiantes y
       administradores. No esta implementado, y se decidio no implementarlo.

       Lo que hay: tokens JWT firmados con HS256 (PyJWT), contraseñas con bcrypt, y autorizacion
       por los tres roles del dominio —STUDENT, PROFESSOR, ADMIN—. La clave de firma vive en el
       Key Vault y App Service la resuelve con su identidad administrada mediante la referencia
       `@Microsoft.KeyVault(...)` de `ajustes.bicep`: no hay ninguna credencial en el codigo ni
       en la configuracion del servicio.

       POR QUE NO SE IMPLEMENTA

       Son de 3 a 5 dias de trabajo, y la asignatura evalua arquitectura de nube, no
       implementacion de identidad. Meterlo antes de la entrega es riesgo sin ganancia en lo que
       se califica. Ademas añadiria una dependencia de pago que el credito academico no absorbe
       bien.

       CUIDADO CON CONFUNDIR DOS COSAS QUE SE LLAMAN PARECIDO

       El documento mezcla en un mismo parrafo dos usos de Entra, y solo uno es falso:

         - **Entra External ID** para los usuarios finales -> NO implementado.
         - **Entra ID y Azure RBAC** para el plano de control -> SI, y funcionando. Es lo que
           sostiene las identidades administradas, el permiso `AcrPull` con el que el contenedor
           descarga su imagen, y el acceso de la aplicacion al Key Vault.

       Al corregir el documento hay que separarlos, no borrar Entra: el segundo uso es real y es
       justo lo que una asignatura de nube quiere ver.

   7.9 Application Insights existe, pero la API todavia no le envia nada
       ACTUALIZADO con las secciones 10 a 15 del documento: el componente de Application
       Insights se crea en el grupo persistente, sobre el MISMO workspace, y la API recibe
       `APPLICATIONINSIGHTS_CONNECTION_STRING`. Lo que sigue sin hacerse es instrumentar el
       codigo (la «Parte A» del documento), asi que la tabla `AppRequests` esta vacia. Por eso
       las alertas 2 y 6 leen `AppServiceHTTPLogs`, que la plataforma escribe sin tocar el
       codigo; al instrumentar la API se cambia la tabla de esas dos consultas. Lo de abajo
       explica por que los registros se resolvieron primero con Log Analytics.

       El documento nombra Azure Monitor y Application Insights para metricas y registros.

       Las METRICAS de plataforma si las recoge Azure Monitor por su cuenta, sin desplegar nada:
       son las que consume la regla de autoescalado para leer la CPU.

       Los REGISTROS son otra cosa. La aplicacion ya los escribia en JSON con un identificador
       por peticion —pensados justo para esto— pero iban a la salida estandar del contenedor y
       ahi se perdian al reciclarse la instancia. Con el autoescalado eso es peor de lo que
       parece: la peticion lenta que alguien reporta ocurrio en una instancia que quiza ya no
       existe.

       Se despliega un area de LOG ANALYTICS en el grupo persistente, con ajustes de diagnostico
       que le envian la salida de la aplicacion y la del cortafuegos. No se usa Application
       Insights porque exigiria instrumentar el codigo con su SDK, y lo que hace falta —poder
       consultar los registros que ya se emiten— lo cubre Log Analytics sin tocar la aplicacion.

       Vive en el grupo persistente a proposito: la infraestructura es efimera, la observabilidad
       se acumula. No cuesta nada parada.

   7.10 Los cinco perfiles RBAC estan en el codigo y no se asignan a nadie (EXCEPCION, 13.2)
       La seccion 10.1 asigna cada perfil a un GRUPO de Entra ID. La cuenta del proyecto es de
       estudiante en el directorio de la universidad y no puede crear grupos
       (`allowedToCreateSecurityGroups = false`, comprobado el 2026-10-29). Asignar a usuarios
       sueltos contradiria 10.1.

       Las asignaciones estan escritas y se condicionan a que su grupo tenga identificador: hoy
       van vacios y no se crea ninguna. Se activan sin tocar el Bicep el dia que TI cree los
       grupos y alguien ponga sus identificadores en los archivos de parametros.

         Motivo       la cuenta no tiene permiso de directorio para crear grupos
         Alcance      los cinco perfiles humanos; la identidad de la API SI tiene su rol
         Responsable  el equipo, a traves de TI de la universidad
         Vencimiento  la entrega final del proyecto

   7.11 Los grupos de recursos se llaman `matricula-*`, no `rg-flexgrade-*`
       El documento propone el prefijo como convencion. Renombrar obligaria a recrear el Key
       Vault —90 dias de borrado logico— y el registro. La consulta de auditoria de 11.3 filtra
       por `matricula-` en vez de `rg-flexgrade`.

       Tampoco hay un tercer grupo de observabilidad: el workspace ya vivia en el persistente.

   7.12 La entrada por el puerto 80 sigue en HTTP (limitacion, 10.2)
       No hay dominio propio ni certificado para terminar TLS en el gateway. Del gateway hacia
       dentro todo va cifrado: 443 al App Service, TLS 1.2 obligatorio en PostgreSQL y TLS en el
       10000 de Redis.

   7.13 Los NSG decian 6380 para Redis, y es 10000
       Era el puerto del Azure Cache for Redis retirado (7.5). No rompia nada —la salida dentro
       de la VNet esta permitida por defecto y la subred del punto de conexion no evalua su
       NSG—, pero declaraba un puerto que ya no existe en el sistema. Corregido.

8. Donde vive cada cosa

   deploy/azure/bicep/main.bicep            la infraestructura efimera completa
   deploy/azure/bicep/base.bicep            lo persistente del grupo base: Key Vault, registro,
                                            workspace, Application Insights y alertas
   deploy/azure/bicep/suscripcion.bicep     lo persistente de la suscripcion: registro de
                                            actividad, presupuesto y gobernanza
   deploy/azure/bicep/parametros/*.json     un archivo por plantilla, mas etiquetas.json
   deploy/azure/bicep/modules/<dominio>/    comun, red, datos, aplicacion, acceso, operacion,
                                            monitoreo, costos, gobernanza y borde
   deploy/azure/RUNBOOK.md                  como levantarla, que mirar y que cuesta
   deploy/azure/scripts/desplegar-base.sh   un comando para lo persistente
   deploy/azure/scripts/levantar.sh         un comando para encenderla
   deploy/azure/scripts/destruir.sh         un comando para apagarla
   deploy/azure/scripts/estado.sh           ¿hay algo encendido y cuanto lleva costando?
   deploy/azure/scripts/validar.sh          valida plantillas, parametros y scripts sin tocar Azure
   deploy/azure/scripts/probar-politicas.sh pruebas positiva y negativas de la gobernanza (13.3)
   deploy/azure/scripts/lib/                lo que comparten los scripts
   deploy/azure/pruebas/                    las pruebas de la infraestructura
   deploy/azure/bicep/modules/operacion/observabilidad.bicep
                                            envia los registros a Log Analytics
