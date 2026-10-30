"""Los archivos de parámetros encajan con sus plantillas y no llevan nada que no deban.

ARM rechaza un parámetro que no existe y uno obligatorio que falta, pero lo hace AL DESPLEGAR: una
errata se descubriría tras crear el grupo. Aquí se descubre en segundos.
"""

import re
import unittest

import apoyo


def _declarados(plantilla: str) -> tuple[set[str], set[str]]:
    parametros = apoyo.compilar(plantilla)["parameters"]
    obligatorios = {n for n, d in parametros.items() if "defaultValue" not in d}
    return set(parametros), obligatorios


def _hojas(valor, ruta=""):
    """Todos los valores escalares de un parámetro, con su ruta, entrando en listas y objetos."""
    if isinstance(valor, dict):
        for clave, interior in valor.items():
            yield from _hojas(interior, f"{ruta}.{clave}")
    elif isinstance(valor, list):
        for i, interior in enumerate(valor):
            yield from _hojas(interior, f"{ruta}[{i}]")
    else:
        yield ruta, valor


class ParametrosContraPlantillas(unittest.TestCase):
    def test_cada_archivo_tiene_plantilla_asignada(self):
        # Un archivo nuevo que nadie empareja no se valida nunca: mejor que la prueba lo exija.
        presentes = {p.name for p in apoyo.PARAMETROS.glob("*.json")}
        conocidos = set(apoyo.PLANTILLA_DE_PERFIL) | {apoyo.PARAMETROS_COMUNES}
        self.assertEqual(presentes, conocidos)

    def test_los_comunes_existen_en_todas_las_plantillas(self):
        # `etiquetas.json` viaja en TODOS los despliegues: un parámetro suyo que falte en una sola
        # plantilla haría que ARM rechazara ese despliegue entero.
        comunes = set(apoyo.leer_parametros(apoyo.PARAMETROS_COMUNES))
        for plantilla in set(apoyo.PLANTILLA_DE_PERFIL.values()):
            declarados, _ = _declarados(plantilla)
            with self.subTest(plantilla=plantilla):
                self.assertLessEqual(comunes, declarados)

    def test_ningun_perfil_sobra_ni_falta(self):
        comunes = set(apoyo.leer_parametros(apoyo.PARAMETROS_COMUNES))
        for perfil, plantilla in apoyo.PLANTILLA_DE_PERFIL.items():
            declarados, obligatorios = _declarados(plantilla)
            dados = set(apoyo.leer_parametros(perfil)) | comunes
            with self.subTest(perfil=perfil):
                self.assertEqual(dados - declarados, set(), "sobran: ARM los rechaza")
                self.assertEqual(obligatorios - dados, set(), "faltan: ARM los pediría")


class ParametrosSanos(unittest.TestCase):
    def test_sin_rutas_corrompidas_por_git_bash(self):
        # Ya pasó: `registrosId` llegó a valer «C:/Program Files/Git/subscriptions/...» porque Git
        # Bash convirtió la ruta al escribirla. El despliegue habría fallado en el módulo de
        # observabilidad, a mitad de camino.
        for perfil in apoyo.PLANTILLA_DE_PERFIL:
            for nombre, parametro in apoyo.leer_parametros(perfil).items():
                for ruta, hoja in _hojas(parametro):
                    if not isinstance(hoja, str):
                        continue
                    with self.subTest(perfil=perfil, parametro=nombre + ruta):
                        self.assertNotIn("Program Files", hoja)
                        self.assertIsNone(re.match(r"^[A-Za-z]:[/\\]", hoja))
                        if "/providers/" in hoja:
                            self.assertTrue(hoja.startswith("/subscriptions/"), hoja)

    def test_ningun_secreto_escrito(self):
        # Los secretos van como REFERENCIA al Key Vault (9.2), nunca como valor.
        sospechoso = re.compile(r"clave|password|secret|contrase", re.I)
        for perfil in [*apoyo.PLANTILLA_DE_PERFIL, apoyo.PARAMETROS_COMUNES]:
            for nombre, parametro in apoyo.leer_parametros(perfil).items():
                if sospechoso.search(nombre):
                    with self.subTest(perfil=perfil, parametro=nombre):
                        self.assertIn("reference", parametro)
                        self.assertNotIn("value", parametro)

    def test_inicio_del_presupuesto_es_primero_de_mes(self):
        inicio = apoyo.valor(apoyo.leer_parametros("suscripcion.json")["inicioPresupuesto"])
        if inicio:
            self.assertRegex(inicio, r"^\d{4}-\d{2}-01$")

    def test_politicas_nacen_en_auditoria(self):
        # 13.3: toda regla nace en Audit/DoNotEnforce. Pasar a `enforce` es una decisión que se
        # toma después de validar, y tiene que ser un cambio consciente en este archivo.
        modo = apoyo.valor(apoyo.leer_parametros("suscripcion.json")["modoPoliticas"])
        self.assertEqual(modo, "audit")


if __name__ == "__main__":
    unittest.main()
