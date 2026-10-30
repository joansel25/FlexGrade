"""IAM y cifrado en tránsito: secciones 10.1, 10.2 y 10.3."""

import re
import unittest

import apoyo


def _roles() -> dict[str, str]:
    return apoyo.compilar("modules/comun/roles.bicep")["variables"]["roles"]


class KeyVault(unittest.TestCase):
    def setUp(self):
        (self.almacen,) = apoyo.de_tipo(apoyo.compilar("base.bicep"), "Microsoft.KeyVault/vaults")

    def test_rbac_sin_politicas_de_acceso(self):
        propiedades = self.almacen["properties"]
        self.assertIs(propiedades["enableRbacAuthorization"], True)
        self.assertNotIn("accessPolicies", propiedades)

    def test_ninguna_politica_de_acceso_en_ninguna_plantilla(self):
        # La política de acceso con `add` de la versión anterior la borraba cualquier redespliegue
        # de base.bicep. Que no vuelva por ningún camino.
        for entrada in ("main.bicep", "base.bicep", "suscripcion.bicep"):
            with self.subTest(entrada=entrada):
                tipo = "Microsoft.KeyVault/vaults/accessPolicies"
                self.assertEqual(apoyo.de_tipo(apoyo.compilar(entrada), tipo), [])

    def test_borrado_logico_y_purga_por_parametro(self):
        propiedades = self.almacen["properties"]
        self.assertIs(propiedades["enableSoftDelete"], True)
        self.assertIn("protegerPurgaKeyVault", propiedades["enablePurgeProtection"])
        # Sin valor por defecto: es irreversible y tiene que decidirse a conciencia.
        parametro = apoyo.compilar("base.bicep")["parameters"]["protegerPurgaKeyVault"]
        self.assertNotIn("defaultValue", parametro)

    def test_registro_de_auditoria(self):
        diagnosticos = apoyo.compilar("base.bicep")["resources"]["diagnosticoKeyVault"]
        self.assertEqual(diagnosticos["properties"]["logs"], [{"categoryGroup": "audit", "enabled": True}])


class IdentidadDeLaApi(unittest.TestCase):
    def test_un_solo_rol_sobre_el_almacen(self):
        roles = _roles()
        permisos = apoyo.plantilla_de_modulo(apoyo.compilar("main.bicep"), "permisos")
        sobre_el_almacen = [
            r
            for r in apoyo.recursos(permisos)
            if r[1]["type"] == "Microsoft.Authorization/roleAssignments" and "vaults" in r[1].get("scope", "")
        ]
        self.assertEqual(len(sobre_el_almacen), 1)
        asignacion = sobre_el_almacen[0][1]["properties"]
        self.assertEqual(asignacion["principalType"], "ServicePrincipal")
        self.assertIn("keyVaultSecretsUser", asignacion["roleDefinitionId"])
        self.assertEqual(roles["keyVaultSecretsUser"], "4633458b-17de-408a-b874-0445c86b69e6")

    def test_secrets_officer_no_esta_en_bicep(self):
        # 10.1: se asigna de forma temporal y registrada, nunca declarada.
        officer = "b86a8fe4-44ce-4948-aee5-eccb2c155cd7"
        for archivo in apoyo.BICEP.rglob("*.bicep"):
            with self.subTest(archivo=archivo.name):
                self.assertNotIn(officer, archivo.read_text(encoding="utf-8"))


class PerfilesHumanos(unittest.TestCase):
    def setUp(self):
        self.fuente = (apoyo.MODULOS / "acceso" / "perfiles-grupo.bicep").read_text(encoding="utf-8")
        self.roles = _roles()

    def _delegables(self) -> list[str]:
        bloque = re.search(r"var rolesDelegables = \[(.*?)\]", self.fuente, re.S).group(1)
        return re.findall(r"roles\.(\w+)", bloque)

    def test_la_delegacion_no_permite_escalar(self):
        # Con Contributor, Owner o el propio RBAC Administrator en la lista, quien delega podría
        # darse más poder del que tiene.
        delegables = self._delegables()
        for prohibido in ("contributor", "rbacAdministrator"):
            with self.subTest(rol=prohibido):
                self.assertNotIn(prohibido, delegables)
        for nombre in delegables:
            self.assertIn(nombre, self.roles)

    def test_condicion_abac_version_2(self):
        self.assertIn("conditionVersion: empty(a.condicion) ? null : '2.0'", self.fuente)
        for accion in ("roleAssignments/write", "roleAssignments/delete"):
            with self.subTest(accion=accion):
                self.assertIn(f"ActionMatches{{\\'Microsoft.Authorization/{accion}\\'}}", self.fuente)

    def test_sin_grupos_no_se_asigna_nada(self):
        # Hoy los grupos de Entra no existen (la cuenta no puede crearlos). Un ID vacío no puede
        # acabar en una asignación: ARM la rechazaría y tumbaría el despliegue.
        self.assertIn("a => !empty(a.principal)", self.fuente)
        for perfil in ("economico.json", "demo.json", "base.json"):
            grupos = apoyo.valor(apoyo.leer_parametros(perfil)["grupos"])
            with self.subTest(perfil=perfil):
                self.assertEqual(set(grupos), {"infraestructura", "desarrollo", "seguridad", "monitoreo", "finops"})

    def test_asignaciones_a_grupos(self):
        for entrada in ("main.bicep", "base.bicep", "suscripcion.bicep"):
            for ruta, recurso in apoyo.recursos(apoyo.compilar(entrada)):
                if recurso["type"] != "Microsoft.Authorization/roleAssignments":
                    continue
                tipo = recurso["properties"]["principalType"]
                with self.subTest(entrada=entrada, asignacion=ruta):
                    # Identidades administradas o grupos: nunca usuarios sueltos (10.1).
                    self.assertIn(tipo, ("Group", "ServicePrincipal"))


class CifradoEnTransito(unittest.TestCase):
    def setUp(self):
        self.main = apoyo.compilar("main.bicep")

    def test_app_service(self):
        (sitio,) = apoyo.de_tipo(self.main, "Microsoft.Web/sites")
        propiedades = sitio["properties"]
        self.assertIs(propiedades["httpsOnly"], True)
        self.assertEqual(propiedades["siteConfig"]["minTlsVersion"], "1.2")
        self.assertEqual(propiedades["siteConfig"]["ftpsState"], "Disabled")
        self.assertEqual(propiedades["siteConfig"]["healthCheckPath"], "/health")

    def test_postgres_tls_y_en_fila(self):
        configuraciones = apoyo.de_tipo(self.main, "Microsoft.DBforPostgreSQL/flexibleServers/configurations")
        por_nombre = {re.search(r"'([\w.]+)'\)\]$", c["name"]).group(1): c for c in configuraciones}
        self.assertEqual(por_nombre["require_secure_transport"]["properties"]["value"], "ON")
        self.assertEqual(por_nombre["ssl_min_protocol_version"]["properties"]["value"], "TLSv1.2")
        # En fila: Flexible Server rechaza cambios de configuración simultáneos (ServerIsBusy).
        cadena = [("require_secure_transport", "azure.extensions"), ("ssl_min_protocol_version", "require_secure_transport")]
        for configuracion, anterior in cadena:
            with self.subTest(configuracion=configuracion):
                dependencias = " ".join(por_nombre[configuracion].get("dependsOn", []))
                self.assertIn(f"'{anterior}')", dependencias)

    def test_redis(self):
        redis = apoyo.plantilla_de_modulo(self.main, "redis")
        (cluster,) = apoyo.de_tipo(redis, "Microsoft.Cache/redisEnterprise")
        (base,) = apoyo.de_tipo(redis, "Microsoft.Cache/redisEnterprise/databases")
        self.assertEqual(cluster["properties"]["minimumTlsVersion"], "1.2")
        self.assertEqual(base["properties"]["clientProtocol"], "Encrypted")
        self.assertEqual(redis["variables"]["puertoTls"], 10000)

    def test_puertos_de_la_red(self):
        # 8.1: 5432 PostgreSQL y 10000 Redis con TLS. El 6380 era del servicio retirado.
        red = apoyo.plantilla_de_modulo(self.main, "red")
        puertos = set()
        for grupo in apoyo.de_tipo(red, "Microsoft.Network/networkSecurityGroups"):
            for regla in grupo["properties"]["securityRules"]:
                p = regla["properties"]
                puertos.update(p.get("destinationPortRanges", []))
                puertos.add(p.get("destinationPortRange"))
        self.assertNotIn("6380", puertos)
        self.assertNotIn("6379", puertos)
        self.assertIn("10000", puertos)
        self.assertIn("5432", puertos)

    def test_sonda_del_gateway_por_443(self):
        (gateway,) = apoyo.de_tipo(self.main, "Microsoft.Network/applicationGateways")
        propiedades = gateway["properties"]
        (sonda,) = propiedades["probes"]
        self.assertEqual(sonda["properties"]["protocol"], "Https")
        self.assertEqual(sonda["properties"]["path"], "/health")
        (ajustes,) = propiedades["backendHttpSettingsCollection"]
        self.assertEqual(ajustes["properties"]["port"], 443)
        # La entrada por 80 NO se cambia: queda documentada como limitación (10.2).
        self.assertEqual([p["properties"]["port"] for p in propiedades["frontendPorts"]], [80])


if __name__ == "__main__":
    unittest.main()
