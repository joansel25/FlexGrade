"""Observabilidad y alertas: secciones 11.1, 11.2 y 11.3."""

import unittest

import apoyo

TODOS_LOS_LOGS = [{"categoryGroup": "allLogs", "enabled": True}]
TODAS_LAS_METRICAS = [{"category": "AllMetrics", "enabled": True}]


class Diagnosticos(unittest.TestCase):
    def setUp(self):
        self.modulo = apoyo.plantilla_de_modulo(apoyo.compilar("main.bicep"), "observabilidad")
        self.variables = self.modulo["variables"]
        self.diagnosticos = {
            r["scope"]: r["properties"]
            for r in apoyo.de_tipo(self.modulo, "Microsoft.Insights/diagnosticSettings")
        }

    def _de(self, tipo: str) -> dict:
        (propiedades,) = [p for alcance, p in self.diagnosticos.items() if tipo in alcance]
        return propiedades

    def _resuelto(self, valor):
        # `logs` y `metrics` llegan como referencia a la variable compartida.
        if isinstance(valor, str) and valor.startswith("[variables('"):
            return self.variables[valor[len("[variables('") : -len("')]")]]
        return valor

    def test_api_postgres_y_gateway_con_todo(self):
        for tipo in ("Microsoft.Web/sites", "Microsoft.DBforPostgreSQL/flexibleServers", "Microsoft.Network/applicationGateways"):
            propiedades = self._de(tipo)
            with self.subTest(recurso=tipo):
                self.assertEqual(self._resuelto(propiedades["logs"]), TODOS_LOS_LOGS)
                self.assertEqual(self._resuelto(propiedades["metrics"]), TODAS_LAS_METRICAS)

    def test_plan_solo_metricas_para_la_alerta_1(self):
        propiedades = self._de("Microsoft.Web/serverfarms")
        self.assertEqual(self._resuelto(propiedades["metrics"]), TODAS_LAS_METRICAS)
        self.assertNotIn("logs", propiedades)


class Telemetria(unittest.TestCase):
    def setUp(self):
        self.modulo = apoyo.plantilla_de_modulo(apoyo.compilar("base.bicep"), "telemetria")

    def test_app_insights_sobre_el_workspace_existente(self):
        (componente,) = apoyo.de_tipo(self.modulo, "Microsoft.Insights/components")
        self.assertEqual(componente["kind"], "web")
        self.assertIn("WorkspaceResourceId", componente["properties"])
        # 11.1: no se crea otro workspace.
        self.assertEqual(apoyo.de_tipo(self.modulo, "Microsoft.OperationalInsights/workspaces"), [])

    def test_retencion_de_auditoria(self):
        self.assertEqual(self.modulo["variables"]["tablasDeAuditoria"], ["AzureActivity", "AppServiceConsoleLogs"])
        base = apoyo.leer_parametros("base.json")
        self.assertEqual(apoyo.valor(base["retencionGeneralDias"]), 30)
        self.assertEqual(apoyo.valor(base["retencionAuditoriaDias"]), 90)

    def test_la_api_recibe_la_cadena_de_conexion(self):
        ajustes = apoyo.plantilla_de_modulo(apoyo.compilar("main.bicep"), "ajustes")
        (config,) = apoyo.de_tipo(ajustes, "Microsoft.Web/sites/config")
        self.assertIn("APPLICATIONINSIGHTS_CONNECTION_STRING", config["properties"])


class RegistroDeActividad(unittest.TestCase):
    def test_las_cuatro_categorias(self):
        (exportacion,) = apoyo.de_tipo(apoyo.compilar("suscripcion.bicep"), "Microsoft.Insights/diagnosticSettings")
        categorias = {l["category"] for l in exportacion["properties"]["logs"] if l["enabled"]}
        self.assertEqual(categorias, {"Administrative", "Security", "Policy", "Autoscale"})


class Alertas(unittest.TestCase):
    # nombre: (tabla, agregación, columna, umbral, ventana, frecuencia, periodos), según 11.1.
    ESPERADAS = {
        "saturacion-cpu": ("AzureMetrics", "Average", "Average", 85, "PT5M", "PT5M", 2),
        "errores-api": ("AppServiceHTTPLogs", "Count", "", 0, "PT5M", "PT1M", 1),
        "disponibilidad": ("AzureMetrics", "Minimum", "Minimum", 0, "PT1M", "PT1M", 3),
        "accesos-inusuales": ("AppServiceHTTPLogs", "Count", "", 0, "PT5M", "PT1M", 1),
    }

    def setUp(self):
        self.base = apoyo.compilar("base.bicep")
        self.registros = apoyo.plantilla_de_modulo(self.base, "alertasDeRegistros")

    def test_las_cuatro_alertas_de_logs(self):
        reglas = {r["nombre"]: r for r in self.registros["variables"]["reglas"]}
        self.assertEqual(set(reglas), set(self.ESPERADAS))
        for nombre, (tabla, agregacion, columna, umbral, ventana, frecuencia, periodos) in self.ESPERADAS.items():
            regla = reglas[nombre]
            with self.subTest(alerta=nombre):
                self.assertEqual(regla["agregacion"], agregacion)
                self.assertEqual(regla["columna"], columna)
                self.assertEqual(regla["umbral"], umbral)
                self.assertEqual(regla["ventana"], ventana)
                self.assertEqual(regla["frecuencia"], frecuencia)
                self.assertEqual(regla["periodos"], periodos)
                consulta = (apoyo.MODULOS / "monitoreo" / "consultas" / f"{nombre}.kql").read_text(encoding="utf-8")
                self.assertTrue(consulta.startswith(tabla), consulta)
                self.assertEqual(consulta.count("{{RECURSO}}"), 1)

    def test_las_reglas_leen_el_workspace_y_avisan(self):
        (regla,) = apoyo.de_tipo(self.registros, "Microsoft.Insights/scheduledQueryRules")
        propiedades = regla["properties"]
        self.assertEqual(regla["copy"]["count"], "[length(variables('reglas'))]")
        self.assertEqual(propiedades["scopes"], ["[parameters('registrosId')]"])
        self.assertEqual(propiedades["actions"]["actionGroups"], ["[parameters('grupoAccionesId')]"])

    def test_alerta_5_permisos_y_politicas(self):
        (alerta,) = apoyo.de_tipo(self.base, "Microsoft.Insights/activityLogAlerts")
        operaciones = {c["equals"] for c in alerta["properties"]["condition"]["allOf"][1]["anyOf"]}
        self.assertEqual(
            operaciones,
            {
                "Microsoft.Authorization/roleAssignments/write",
                "Microsoft.Authorization/roleAssignments/delete",
                "Microsoft.Authorization/policyAssignments/write",
                "Microsoft.Authorization/policyAssignments/delete",
            },
        )

    def test_alerta_4_almacenamiento_en_el_grupo_efimero(self):
        postgres = apoyo.plantilla_de_modulo(apoyo.compilar("main.bicep"), "postgres")
        (alerta,) = apoyo.de_tipo(postgres, "Microsoft.Insights/metricAlerts")
        propiedades = alerta["properties"]
        (criterio,) = propiedades["criteria"]["allOf"]
        self.assertEqual(criterio["metricName"], "storage_percent")
        self.assertEqual((criterio["operator"], criterio["threshold"], criterio["timeAggregation"]), ("GreaterThan", 80, "Average"))
        self.assertEqual((propiedades["windowSize"], propiedades["evaluationFrequency"]), ("PT15M", "PT5M"))
        # Solo en el perfil de demostración (1.5).
        self.assertIs(apoyo.valor(apoyo.leer_parametros("demo.json")["desplegarAlertas"]), True)
        self.assertIs(apoyo.valor(apoyo.leer_parametros("economico.json")["desplegarAlertas"]), False)

    def test_el_autoescalado_sigue_en_70(self):
        # La alerta 1 es independiente: la regla de autoescalado no se toca (11.1).
        escalado = apoyo.plantilla_de_modulo(apoyo.compilar("main.bicep"), "escalado")
        self.assertEqual(escalado["variables"]["reglaSubir"]["metricTrigger"]["threshold"], 70)

    def test_grupo_de_acciones(self):
        grupo = apoyo.plantilla_de_modulo(self.base, "grupoAcciones")
        (recurso,) = apoyo.de_tipo(grupo, "Microsoft.Insights/actionGroups")
        self.assertLessEqual(len(recurso["properties"]["groupShortName"]), 12)
        self.assertEqual(recurso["location"], "global")
        self.assertNotIn("defaultValue", grupo["parameters"]["correos"])
        self.assertEqual(grupo["parameters"]["correos"]["minLength"], 1)


if __name__ == "__main__":
    unittest.main()
