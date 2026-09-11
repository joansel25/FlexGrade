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
   Ninguna diferencia es una renuncia: en los cuatro casos el requisito se cumple de otra forma.

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

8. Donde vive cada cosa

   deploy/azure/bicep/main.bicep       la infraestructura efimera completa
   deploy/azure/bicep/base.bicep       Key Vault y registro, que nunca se destruyen
   deploy/azure/bicep/parametros.*.json   los dos perfiles
   deploy/azure/RUNBOOK.md             como levantarla, que mirar y que cuesta
   deploy/azure/levantar.sh|.ps1       un comando para encenderla
   deploy/azure/destruir.sh|.ps1       un comando para apagarla
   deploy/azure/estado.sh|.ps1         ¿hay algo encendido y cuanto lleva costando?
   deploy/azure/validar.sh             valida plantillas y parametros sin tocar Azure
