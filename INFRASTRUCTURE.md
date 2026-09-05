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