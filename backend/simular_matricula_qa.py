"""Simula una ventana de matrícula disputada, para las pruebas de QA manual.

**Esto es un guion de pruebas, no una pieza del producto.** Reproduce lo que el sistema existe
para soportar: mucha gente pulsando «Inscribir» sobre el mismo grupo en el mismo instante.

Hace dos cosas y las dos importan:

1. **Inicia sesión de verdad**, con el mismo endpoint que usa el navegador. Sirve para ver
   cómo se comporta el límite de peticiones cuando muchas personas entran desde la MISMA
   dirección de salida, que es lo que ocurre en un campus con NAT.
2. **Lanza todas las inscripciones a la vez** con hilos, no en fila. Una tras otra no probaría
   nada: la carrera por el último cupo solo existe si las peticiones coinciden.

    docker-compose exec backend python simular_matricula_qa.py MAT101 01 40
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from collections import Counter

BASE = "http://localhost:8000"
PASSWORD = "SecurePass123"


def _pedir(ruta: str, cuerpo: dict | None = None, token: str | None = None) -> tuple[int, dict]:
    cabeceras = {"Content-Type": "application/json"}

    if token:
        cabeceras["Authorization"] = f"Bearer {token}"

    peticion = urllib.request.Request(
        BASE + ruta,
        data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
        headers=cabeceras,
    )

    try:
        with urllib.request.urlopen(peticion) as respuesta:
            return respuesta.status, json.load(respuesta)
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.load(error)
        except Exception:
            return error.code, {}


def iniciar_sesion(indice: int) -> tuple[str, str | None, str | None]:
    correo = f"qa{indice:03d}@tdea.edu.co"
    estado, cuerpo = _pedir("/api/v1/auth/login", {"email": correo, "password": PASSWORD})

    if estado == 200:
        return correo, cuerpo["access_token"], None

    return correo, None, cuerpo.get("error", {}).get("code", f"HTTP_{estado}")


def main(codigo: str, grupo: str, cuantos: int) -> None:
    print(f"1. Iniciando sesión de {cuantos} estudiantes desde la MISMA dirección…")

    with ThreadPoolExecutor(max_workers=20) as pool:
        sesiones = list(pool.map(iniciar_sesion, range(1, cuantos + 1)))

    con_token = [(c, t) for c, t, _ in sesiones if t]
    fallos = Counter(e for _, t, e in sesiones if not t)

    print(f"   entraron: {len(con_token)} · rechazados: {sum(fallos.values())} {dict(fallos)}")

    if not con_token:
        raise SystemExit("Nadie pudo entrar; no hay nada que simular.")

    # El grupo se busca por el catálogo público, igual que lo haría el navegador.
    _, materias = _pedir("/api/v1/courses?size=50")
    curso = next(c for c in materias["items"] if c["code"] == codigo)
    _, grupos = _pedir(f"/api/v1/courses/{curso['id']}/offerings")
    oferta = next(o for o in grupos["offerings"] if o["group_number"] == grupo)

    print(
        f"\n2. {len(con_token)} inscripciones SIMULTÁNEAS sobre {codigo} grupo {grupo} "
        f"({oferta['available_slots']} cupos libres de {oferta['total_capacity']})…"
    )

    def inscribir(sesion: tuple[str, str]) -> str:
        _, token = sesion
        estado, cuerpo = _pedir(
            "/api/v1/enrollments", {"course_offering_id": oferta["id"]}, token=token
        )

        if estado == 201:
            return "INSCRITO"

        return cuerpo.get("error", {}).get("code", f"HTTP_{estado}")

    with ThreadPoolExecutor(max_workers=len(con_token)) as pool:
        resultados = Counter(pool.map(inscribir, con_token))

    for clave, cuantas in resultados.most_common():
        print(f"   {clave}: {cuantas}")

    # La comprobación que de verdad importa: el cupo no se pasó.
    _, grupos = _pedir(f"/api/v1/courses/{curso['id']}/offerings")
    oferta = next(o for o in grupos["offerings"] if o["group_number"] == grupo)
    inscritos = oferta["total_capacity"] - oferta["available_slots"]

    print(f"\n3. Estado final: {inscritos} inscritos de {oferta['total_capacity']} cupos.")
    print("   SIN SOBRECUPO" if inscritos <= oferta["total_capacity"] else "   ¡SOBRECUPO!")


if __name__ == "__main__":
    main(
        sys.argv[1] if len(sys.argv) > 1 else "MAT101",
        sys.argv[2] if len(sys.argv) > 2 else "01",
        int(sys.argv[3]) if len(sys.argv) > 3 else 40,
    )
