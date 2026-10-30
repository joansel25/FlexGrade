"""Etiquetas en todo lo que las admite (12.2) y región restringida (13.2).

Es la comprobación «cada módulo declara y aplica `tags`» de la sección 8 del documento, hecha
sobre el ARM compilado: un recurso nuevo sin etiquetas la rompe aunque nadie se acuerde de mirar.
"""

import unittest

import apoyo

# Lo que Azure Policy evalúa en modo `Indexed`: tipos que admiten etiquetas Y ubicación.
ETIQUETABLES = {
    "Microsoft.Cache/redisEnterprise",
    "Microsoft.ContainerInstance/containerGroups",
    "Microsoft.ContainerRegistry/registries",
    "Microsoft.DBforPostgreSQL/flexibleServers",
    "Microsoft.Insights/actionGroups",
    "Microsoft.Insights/activityLogAlerts",
    "Microsoft.Insights/autoscalesettings",
    "Microsoft.Insights/components",
    "Microsoft.Insights/metricAlerts",
    "Microsoft.Insights/scheduledQueryRules",
    "Microsoft.KeyVault/vaults",
    "Microsoft.ManagedIdentity/userAssignedIdentities",
    "Microsoft.Network/ApplicationGatewayWebApplicationFirewallPolicies",
    "Microsoft.Network/applicationGateways",
    "Microsoft.Network/natGateways",
    "Microsoft.Network/networkSecurityGroups",
    "Microsoft.Network/privateDnsZones",
    "Microsoft.Network/privateDnsZones/virtualNetworkLinks",
    "Microsoft.Network/privateEndpoints",
    "Microsoft.Network/publicIPAddresses",
    "Microsoft.Network/virtualNetworks",
    "Microsoft.OperationalInsights/workspaces",
    "Microsoft.Resources/resourceGroups",
    "Microsoft.Storage/storageAccounts",
    "Microsoft.Web/serverfarms",
    "Microsoft.Web/sites",
}

# Lo que no admite etiquetas o no tiene ubicación propia: Policy no lo evalúa en `Indexed`.
NO_ETIQUETABLES = {
    "Microsoft.Authorization/policyAssignments",
    "Microsoft.Authorization/policyDefinitions",
    "Microsoft.Authorization/policySetDefinitions",
    "Microsoft.Authorization/roleAssignments",
    "Microsoft.Cache/redisEnterprise/databases",
    "Microsoft.Consumption/budgets",
    "Microsoft.DBforPostgreSQL/flexibleServers/configurations",
    "Microsoft.DBforPostgreSQL/flexibleServers/databases",
    "Microsoft.Insights/diagnosticSettings",
    "Microsoft.KeyVault/vaults/secrets",
    "Microsoft.Network/privateEndpoints/privateDnsZoneGroups",
    "Microsoft.OperationalInsights/workspaces/tables",
    "Microsoft.Web/sites/config",
}

ENTRADAS = ["main.bicep", "base.bicep", "suscripcion.bicep"]


class EtiquetasEnTodo(unittest.TestCase):
    def test_todo_tipo_esta_clasificado(self):
        # Un tipo nuevo obliga a decidir si lleva etiquetas: la prueba no lo deja pasar en silencio.
        for entrada in ENTRADAS:
            for ruta, recurso in apoyo.recursos(apoyo.compilar(entrada)):
                with self.subTest(entrada=entrada, recurso=ruta):
                    self.assertIn(recurso["type"], ETIQUETABLES | NO_ETIQUETABLES)

    def test_todo_lo_etiquetable_lleva_tags(self):
        for entrada in ENTRADAS:
            for ruta, recurso in apoyo.recursos(apoyo.compilar(entrada)):
                if recurso["type"] in ETIQUETABLES:
                    with self.subTest(entrada=entrada, recurso=ruta):
                        self.assertTrue(recurso.get("tags"), f"{ruta} sin `tags`")

    def test_las_cuatro_etiquetas_obligatorias(self):
        funcion = apoyo.compilar("base.bicep")["functions"][0]["members"]["etiquetas"]
        cuerpo = funcion["output"]["value"]
        for etiqueta in ("Proyecto", "Dueno", "Ambiente", "CentroCosto", "Vigencia"):
            with self.subTest(etiqueta=etiqueta):
                self.assertIn(f"'{etiqueta}'", cuerpo)
        self.assertIn("'FlexGrade'", cuerpo)

    def test_el_tipo_y_la_lista_de_ambientes_coinciden(self):
        # La política de valores válidos usa la lista; las plantillas, el tipo. Si divergen, la
        # política castigaría un valor que el Bicep acepta, o al revés.
        etiquetas = apoyo.compilar("modules/comun/etiquetas.bicep")
        permitidos = etiquetas["definitions"]["ambienteEtiqueta"]["allowedValues"]
        self.assertEqual(sorted(permitidos), sorted(etiquetas["variables"]["ambientesValidos"]))

    def test_los_perfiles_usan_ambientes_validos(self):
        validos = apoyo.compilar("modules/comun/etiquetas.bicep")["variables"]["ambientesValidos"]
        for perfil in ("economico.json", "demo.json"):
            ambiente = apoyo.valor(apoyo.leer_parametros(perfil)["etiquetaAmbiente"])
            with self.subTest(perfil=perfil):
                self.assertIn(ambiente, validos)

    def test_la_etiqueta_no_es_el_ambiente_de_la_aplicacion(self):
        # Con ENVIRONMENT=dev el backend escribe logs en texto plano (main.py:98) y Log Analytics
        # deja de poder leerlos. La etiqueta `dev` NO puede llegar a la aplicación.
        economico = apoyo.leer_parametros("economico.json")
        self.assertEqual(apoyo.valor(economico["etiquetaAmbiente"]), "dev")
        self.assertNotEqual(apoyo.valor(economico.get("ambiente", {"value": "demo"})), "dev")


class RegionRestringida(unittest.TestCase):
    def test_solo_central_us(self):
        for entrada in ENTRADAS:
            with self.subTest(entrada=entrada):
                ubicacion = apoyo.compilar(entrada)["parameters"]["ubicacion"]
                self.assertEqual(ubicacion["allowedValues"], ["centralus"])


if __name__ == "__main__":
    unittest.main()
