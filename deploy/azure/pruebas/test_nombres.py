"""Los nombres que vigilan las alertas son los mismos que crea la demo.

Las alertas del grupo persistente filtran por el identificador de recursos efímeros. Si `base.bicep`
y `main.bicep` calcularan distinto un solo nombre, la alerta vigilaría un recurso que no existe y
callaría para siempre: un fallo que ninguna otra prueba vería.
"""

import unittest

import apoyo


def _funciones(plantilla: str) -> dict:
    (espacio,) = apoyo.compilar(plantilla)["functions"]
    return {nombre: f["output"]["value"] for nombre, f in espacio["members"].items()}


class NombresCompartidos(unittest.TestCase):
    def test_el_sufijo_se_calcula_igual_en_los_dos_grupos(self):
        base = _funciones("base.bicep")
        main = _funciones("main.bicep")
        self.assertEqual(base["sufijo"], main["calcularSufijo"])
        self.assertEqual(base["idGrupo"], main["idGrupo"])
        self.assertEqual(base["nombresBase"], main["nombresBase"])

    def test_idgrupo_reproduce_resourcegroup_id(self):
        # `resourceGroup().id` es exactamente «/subscriptions/<id>/resourceGroups/<nombre>».
        self.assertEqual(
            _funciones("base.bicep")["idGrupo"],
            "[format('{0}/resourceGroups/{1}', parameters('idSuscripcion'), parameters('nombreGrupo'))]",
        )

    def test_los_modulos_nombran_con_la_misma_funcion_que_las_alertas(self):
        vigilados = _funciones("base.bicep")["nombresEfimeros"]
        main = apoyo.compilar("main.bicep")
        for modulo in ("app", "gateway", "datos"):
            with self.subTest(modulo=modulo):
                plantilla = apoyo.plantilla_de_modulo(main, modulo)
                (espacio,) = plantilla["functions"]
                self.assertEqual(espacio["members"]["nombresEfimeros"]["output"]["value"], vigilados)

    def test_los_recursos_vigilados_usan_esos_nombres(self):
        main = apoyo.compilar("main.bicep")
        casos = {
            ("app", "Microsoft.Web/serverfarms"): "plan",
            ("app", "Microsoft.Web/sites"): "app",
            ("gateway", "Microsoft.Network/applicationGateways"): "gateway",
        }
        for (modulo, tipo), clave in casos.items():
            (recurso,) = apoyo.de_tipo(apoyo.plantilla_de_modulo(main, modulo), tipo)
            with self.subTest(tipo=tipo):
                self.assertEqual(recurso["name"], f"[variables('nombres').{clave}]")
        datos = apoyo.plantilla_de_modulo(main, "datos")
        self.assertEqual(datos["resources"]["postgres"]["properties"]["parameters"]["nombreServidor"]["value"], "[variables('nombres').postgres]")

    def test_los_nombres_de_la_base_no_cambian(self):
        # Los recursos persistentes YA existen con estos nombres: si la función los cambiara, el
        # próximo despliegue crearía un Key Vault y un registro nuevos al lado de los actuales.
        self.assertEqual(
            _funciones("base.bicep")["nombresBase"],
            {
                "acr": "[format('{0}acr{1}', parameters('prefijo'), parameters('sufijo'))]",
                "keyVault": "[format('{0}-kv-{1}', parameters('prefijo'), parameters('sufijo'))]",
                "registros": "[format('{0}-logs-{1}', parameters('prefijo'), parameters('sufijo'))]",
                "appInsights": "[format('{0}-appinsights-{1}', parameters('prefijo'), parameters('sufijo'))]",
                "grupoAcciones": "[format('{0}-alertas', parameters('prefijo'))]",
            },
        )
        demo = apoyo.leer_parametros("demo.json")
        sufijo_real = apoyo.valor(demo["nombreKeyVault"]).removeprefix("matricula-kv-")
        self.assertEqual(apoyo.valor(demo["nombreAcr"]), f"matriculaacr{sufijo_real}")
        self.assertTrue(apoyo.valor(demo["registrosId"]).endswith(f"/matricula-logs-{sufijo_real}"))


if __name__ == "__main__":
    unittest.main()
