"""Los scripts de ciclo de vida, ejecutados de verdad contra un `az` FALSO.

Se copia `scripts/` y los parámetros a un árbol temporal y se ejecutan con bash. Delante en el PATH
va un `az` que no habla con Azure: anota cada llamada y responde lo justo para que el script
avance. Así se prueba el flujo real —qué llama, en qué orden y con qué argumentos— sin una sesión
de Azure ni un céntimo de coste.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import apoyo

AZ_FALSO = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$AZ_REGISTRO"
case "$1 $2" in
  "account show") [[ "$*" == *"--query name"* ]] && echo "Suscripcion de prueba" ;;
  "group exists") echo false ;;
esac
exit 0
"""

BASH = apoyo.bash()


@unittest.skipIf(BASH is None, "no hay bash de Git ni del sistema")
class Scripts(unittest.TestCase):
    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp(prefix="flexgrade-"))
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)
        azure = self.raiz / "deploy" / "azure"
        shutil.copytree(apoyo.SCRIPTS, azure / "scripts")
        shutil.copytree(apoyo.PARAMETROS, azure / "bicep" / "parametros")
        self.parametros = azure / "bicep" / "parametros"
        self.scripts = azure / "scripts"

        binarios = self.raiz / "bin"
        binarios.mkdir()
        az = binarios / "az"
        az.write_text(AZ_FALSO, encoding="utf-8", newline="\n")
        az.chmod(0o755)
        self.registro = self.raiz / "az.log"
        self.registro.touch()
        self.entorno = {
            **os.environ,
            "PATH": f"{binarios}{os.pathsep}{os.environ['PATH']}",
            "AZ_REGISTRO": self.registro.as_posix(),
            "NO_COLOR": "1",
        }

    # --- utilidades -------------------------------------------------------------

    def rellenar(self, archivo: str, valores: dict) -> None:
        ruta = self.parametros / archivo
        documento = json.loads(ruta.read_text(encoding="utf-8"))
        for nombre, valor in valores.items():
            documento["parameters"][nombre] = {"value": valor}
        ruta.write_text(json.dumps(documento, indent=2), encoding="utf-8", newline="\n")

    def rellenar_etiquetas(self) -> None:
        self.rellenar("etiquetas.json", {"dueno": "equipo-flexgrade", "centroCosto": "CC-PRUEBA"})

    def ejecutar(self, script: str, *argumentos: str, entrada: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [BASH, (self.scripts / script).as_posix(), *argumentos],
            env=self.entorno,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=entrada,
            timeout=120,
            check=False,
        )

    def libreria(self, orden: str) -> subprocess.CompletedProcess:
        comun = (self.scripts / "lib" / "comun.sh").as_posix()
        return subprocess.run(
            [BASH, "-c", f'source "{comun}"; {orden}'],
            env=self.entorno,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )

    def llamadas_a_az(self) -> list[str]:
        return [l for l in self.registro.read_text(encoding="utf-8").splitlines() if l]

    # --- la librería ------------------------------------------------------------

    def test_pendientes_coincide_con_las_pruebas(self):
        # Dos implementaciones de la misma regla —una en bash para los scripts y otra en Python
        # para las pruebas— no pueden discrepar sobre qué falta.
        resultado = self.libreria('pendientes "$PARAMETROS"/*.json')
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        desde_bash = sorted(tuple(l.split(": ")) for l in resultado.stdout.splitlines())
        self.assertEqual(desde_bash, sorted(apoyo.pendientes()))
        lista_bash = re.search(r'PENDIENTES_DEL_EQUIPO="([^"]+)"', (apoyo.SCRIPTS / "lib" / "perfil.sh").read_text(encoding="utf-8"))
        self.assertEqual(set(lista_bash.group(1).split()), apoyo.PENDIENTES_DEL_EQUIPO)

    def test_etiquetas_de_un_grupo_efimero(self):
        self.rellenar_etiquetas()
        resultado = self.libreria("etiquetas_de_grupo demo 2026-10-30")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(
            resultado.stdout.splitlines(),
            ["Proyecto=FlexGrade", "Dueno=equipo-flexgrade", "Ambiente=demo", "CentroCosto=CC-PRUEBA", "Vigencia=2026-10-30"],
        )

    def test_el_grupo_persistente_no_caduca(self):
        self.rellenar_etiquetas()
        resultado = self.libreria("etiquetas_de_grupo compartido")
        self.assertNotIn("Vigencia", resultado.stdout)
        self.assertEqual(len(resultado.stdout.splitlines()), 4)

    def test_sin_dueno_no_hay_etiquetas(self):
        resultado = self.libreria("etiquetas_de_grupo demo 2026-10-30")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("dueno", resultado.stderr)

    # --- los scripts se paran ANTES de tocar Azure --------------------------------

    def test_sin_valores_del_equipo_nadie_llama_a_azure(self):
        for script, argumentos in (
            ("levantar.sh", ["demo", "--ensayo"]),
            ("desplegar-base.sh", ["--ensayo"]),
            ("probar-politicas.sh", []),
        ):
            with self.subTest(script=script):
                self.registro.write_text("", encoding="utf-8")
                resultado = self.ejecutar(script, *argumentos)
                self.assertNotEqual(resultado.returncode, 0)
                self.assertIn("Faltan valores que define el equipo", resultado.stdout + resultado.stderr)
                self.assertEqual(self.llamadas_a_az(), [], "llamó a az antes de comprobar los valores")

    # --- el flujo de levantar.sh ---------------------------------------------------

    def test_el_ensayo_crea_el_grupo_etiquetado_y_no_despliega(self):
        self.rellenar_etiquetas()
        resultado = self.ejecutar("levantar.sh", "demo", "--ensayo")
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)

        llamadas = self.llamadas_a_az()
        (creacion,) = [l for l in llamadas if l.startswith("group create")]
        for etiqueta in ("Proyecto=FlexGrade", "Dueno=equipo-flexgrade", "Ambiente=demo", "CentroCosto=CC-PRUEBA"):
            self.assertIn(etiqueta, creacion)
        self.assertRegex(creacion, r"Vigencia=\d{4}-\d{2}-\d{2}")

        (ensayo,) = [l for l in llamadas if l.startswith("deployment group what-if")]
        self.assertIn("@parametros/demo.json @parametros/etiquetas.json", ensayo)
        self.assertRegex(ensayo, r"vigencia=\d{4}-\d{2}-\d{2}")
        # Un ensayo nunca despliega.
        self.assertEqual([l for l in llamadas if l.startswith("deployment group create")], [])

    def test_el_perfil_economico_se_etiqueta_como_dev(self):
        self.rellenar_etiquetas()
        resultado = self.ejecutar("levantar.sh", "economico", "--ensayo")
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        (creacion,) = [l for l in self.llamadas_a_az() if l.startswith("group create")]
        self.assertIn("Ambiente=dev", creacion)

    # --- el flujo de desplegar-base.sh ------------------------------------------------

    def test_desplegar_base_va_en_orden_y_con_las_etiquetas_comunes(self):
        self.rellenar_etiquetas()
        self.rellenar("base.json", {"correosAlertas": ["equipo@ejemplo.edu.co"]})
        self.rellenar(
            "suscripcion.json",
            {"montoPresupuesto": 100, "inicioPresupuesto": "2026-11-01", "correosPresupuesto": ["equipo@ejemplo.edu.co"]},
        )
        resultado = self.ejecutar("desplegar-base.sh", "--ensayo")
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)

        despliegues = [l for l in self.llamadas_a_az() if l.startswith("deployment ")]
        self.assertEqual(len(despliegues), 2)
        base, suscripcion = despliegues
        # Primero la base: la suscripción lee de ella el workspace y el grupo de acciones.
        self.assertTrue(base.startswith("deployment group what-if"), base)
        self.assertIn("--template-file base.bicep", base)
        self.assertTrue(suscripcion.startswith("deployment sub what-if"), suscripcion)
        self.assertIn("--template-file suscripcion.bicep", suscripcion)
        for despliegue in despliegues:
            self.assertIn("@parametros/etiquetas.json", despliegue)

    def test_probar_politicas_se_niega_en_modo_auditoria(self):
        self.rellenar_etiquetas()
        az = self.raiz / "bin" / "az"
        az.write_text(AZ_FALSO.replace('  "group exists")', '  "policy assignment") echo DoNotEnforce ;;\n  "group exists")'), encoding="utf-8", newline="\n")
        resultado = self.ejecutar("probar-politicas.sh")
        self.assertNotEqual(resultado.returncode, 0)
        self.assertIn("modo audit", resultado.stdout + resultado.stderr)
        self.assertEqual([l for l in self.llamadas_a_az() if l.startswith("group create")], [])


if __name__ == "__main__":
    unittest.main()
