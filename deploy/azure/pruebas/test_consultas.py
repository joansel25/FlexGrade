"""Las consultas de las alertas se EJECUTAN contra el workspace real.

Una alerta de logs con una columna mal escrita se despliega sin error y no dispara nunca: Azure
solo valida la consulta al evaluarla. Esta prueba las corre de verdad, sobre las últimas 24 horas,
y falla si una tabla o una columna no existe.

Solo lee, no cuesta nada y no despliega nada, pero necesita una sesión de Azure. Por eso solo
corre con `FLEXGRADE_PRUEBAS_AZURE=1`; en el CI, sin credenciales, se salta.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import apoyo

CONSULTAS = apoyo.MODULOS / "monitoreo" / "consultas"


def _workspace() -> str:
    """El identificador de cliente del workspace persistente, que es lo que pide la consulta."""
    registros_id = apoyo.valor(apoyo.leer_parametros("demo.json")["registrosId"])
    resultado = subprocess.run(
        [shutil.which("az"), "monitor", "log-analytics", "workspace", "show", "--ids", registros_id, "--query", "customerId", "-o", "tsv"],
        capture_output=True,
        check=True,
    )
    return resultado.stdout.decode().strip()


@unittest.skipUnless(os.environ.get("FLEXGRADE_PRUEBAS_AZURE") == "1", "solo con FLEXGRADE_PRUEBAS_AZURE=1 y sesión de Azure")
class ConsultasEnElWorkspaceReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = _workspace()
        # Un identificador con el formato real: la consulta tiene que ser válida, aunque hoy no
        # haya ningún recurso con ese nombre.
        cls.recurso = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/matricula-demo/providers/Microsoft.Web/sites/matricula-api-prueba"

    def test_todas_las_consultas_son_validas(self):
        archivos = sorted(CONSULTAS.glob("*.kql"))
        self.assertEqual(len(archivos), 4)
        for archivo in archivos:
            consulta = archivo.read_text(encoding="utf-8").replace("{{RECURSO}}", self.recurso)
            with self.subTest(consulta=archivo.name):
                # Por la API REST de Log Analytics con `az rest`, que viene con la CLI.
                # `az monitor log-analytics query` vive en una extensión que no siempre está.
                #
                # El cuerpo va en un ARCHIVO: en Windows `az` es un `.cmd`, y `cmd.exe` toma el `|`
                # de KQL que vaya en un argumento como una tubería y parte el comando en dos.
                with tempfile.TemporaryDirectory() as carpeta:
                    cuerpo = Path(carpeta) / "consulta.json"
                    cuerpo.write_text(json.dumps({"query": consulta, "timespan": "P1D"}), encoding="utf-8")
                    resultado = subprocess.run(
                        [shutil.which("az"), "rest", "--method", "post",
                         "--url", f"https://api.loganalytics.io/v1/workspaces/{self.workspace}/query",
                         "--resource", "https://api.loganalytics.io",
                         "--headers", "Content-Type=application/json",
                         "--body", f"@{cuerpo}", "-o", "json"],
                        capture_output=True,
                        check=False,
                    )
                error = resultado.stderr.decode("utf-8", errors="replace")
                self.assertEqual(resultado.returncode, 0, error)
                # La respuesta trae la tabla con sus columnas: vacía de filas hoy, con la demo apagada.
                respuesta = json.loads(resultado.stdout.decode("utf-8", errors="replace"))
                self.assertIn("columns", respuesta["tables"][0])


if __name__ == "__main__":
    unittest.main()
