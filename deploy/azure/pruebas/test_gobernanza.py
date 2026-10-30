"""Costos y gobernanza: secciones 12.3 y 13.3."""

import unittest

import apoyo

INTEGRADAS = {
    "postgresSinAccesoPublico": "5e1de0e3-42cb-4ebc-a86d-61d0c619ca48",
    "etiquetaEnRecursos": "871b6d14-10aa-478d-b590-94f262ecfa99",
    "etiquetaEnGrupos": "96670d01-0a4d-4649-9c89-2d3abc0a5025",
    "appServiceSoloHttps": "a4af4a39-4135-47fb-b175-47fbdf85311d",
    "postgresSslObligatorio": "c29c38cb-74a7-4505-9a06-e588ab86620a",
    "logsDeKeyVault": "cf820ca0-f99e-4f3e-84fb-66e913812d21",
    "logsDeAppService": "91a78b24-f231-4a8a-8da9-02c35b2b6510",
}


class Presupuesto(unittest.TestCase):
    def setUp(self):
        self.modulo = apoyo.plantilla_de_modulo(apoyo.compilar("suscripcion.bicep"), "presupuesto")

    def test_tres_avisos(self):
        avisos = {(a["umbral"], a["tipo"]) for a in self.modulo["variables"]["avisos"].values()}
        self.assertEqual(avisos, {(80, "Actual"), (100, "Forecasted"), (100, "Actual")})

    def test_avisa_no_detiene(self):
        (presupuesto,) = apoyo.de_tipo(self.modulo, "Microsoft.Consumption/budgets")
        self.assertEqual(presupuesto["properties"]["timeGrain"], "Monthly")
        self.assertNotIn("actions", presupuesto["properties"])

    def test_monto_sin_valor_inventado(self):
        monto = apoyo.compilar("suscripcion.bicep")["parameters"]["montoPresupuesto"]
        self.assertNotIn("defaultValue", monto)
        self.assertEqual(monto["minValue"], 1)


class Iniciativa(unittest.TestCase):
    def setUp(self):
        self.modulo = apoyo.plantilla_de_modulo(apoyo.compilar("suscripcion.bicep"), "iniciativa")
        self.variables = self.modulo["variables"]

    def test_integradas_resueltas(self):
        self.assertEqual(self.variables["integradas"], INTEGRADAS)

    def test_cuatro_etiquetas_en_recursos_y_en_grupos(self):
        self.assertEqual(self.variables["etiquetasObligatorias"], ["Proyecto", "Dueno", "Ambiente", "CentroCosto"])
        # Una variable con bucle no queda como clave propia: ARM la guarda dentro de `copy`.
        (por_etiqueta,) = [c for c in self.variables["copy"] if c["name"] == "referenciasPorEtiqueta"]
        # Es un bucle: dos referencias —en recursos y en grupos— por cada una de las cuatro.
        self.assertEqual(por_etiqueta["count"], "[length(variables('etiquetasObligatorias'))]")
        entrada = por_etiqueta["input"]
        self.assertEqual(entrada.count("etiqueta-en-recursos-"), 1)
        self.assertEqual(entrada.count("etiqueta-en-grupos-"), 1)
        self.assertIn("etiquetaEnRecursos", entrada)
        self.assertIn("etiquetaEnGrupos", entrada)

    def test_regla_personalizada(self):
        (definicion,) = apoyo.de_tipo(self.modulo, "Microsoft.Authorization/policyDefinitions")
        propiedades = definicion["properties"]
        self.assertEqual(propiedades["mode"], "Indexed")
        # El efecto tiene que llegar a Azure como expresión de la POLÍTICA, no evaluarse al
        # desplegar: por eso va escapado con `[[`.
        self.assertEqual(propiedades["policyRule"]["then"]["effect"], "[[parameters('efecto')]")
        self.assertEqual(propiedades["parameters"]["efecto"]["allowedValues"], ["Audit", "Deny"])

    def test_efectos_escapados_en_la_iniciativa(self):
        for referencia in self.variables["referenciasFijas"]:
            for parametro in referencia.get("parameters", {}).values():
                if "efecto" in str(parametro["value"]):
                    with self.subTest(referencia=referencia["policyDefinitionReferenceId"]):
                        self.assertTrue(parametro["value"].startswith("[["))

    def test_sin_remediacion_automatica(self):
        # 13.3: ni Modify ni DeployIfNotExists. Se corrige el Bicep.
        texto = str(self.modulo)
        for efecto in ("Modify", "DeployIfNotExists"):
            with self.subTest(efecto=efecto):
                self.assertNotIn(efecto, texto)


class Asignacion(unittest.TestCase):
    def setUp(self):
        self.suscripcion = apoyo.compilar("suscripcion.bicep")
        self.modulo = apoyo.plantilla_de_modulo(self.suscripcion, "asignacion")

    def test_un_parametro_mueve_las_dos_palancas(self):
        (asignacion,) = apoyo.de_tipo(self.modulo, "Microsoft.Authorization/policyAssignments")
        propiedades = asignacion["properties"]
        self.assertIn("'Default'", propiedades["enforcementMode"])
        self.assertIn("'DoNotEnforce'", propiedades["enforcementMode"])
        self.assertIn("'Deny'", propiedades["parameters"]["efecto"]["value"])
        self.assertIn("'Audit'", propiedades["parameters"]["efecto"]["value"])
        self.assertEqual(self.modulo["variables"]["bloquear"], "[equals(parameters('modo'), 'enforce')]")
        self.assertNotIn("identity", asignacion)

    def test_auditoria_por_defecto_y_network_watcher_fuera(self):
        parametros = self.suscripcion["parameters"]
        self.assertEqual(parametros["modoPoliticas"]["defaultValue"], "audit")
        self.assertEqual(parametros["gruposExcluidosDePoliticas"]["defaultValue"], ["NetworkWatcherRG"])


if __name__ == "__main__":
    unittest.main()
