"""
Generador de carga para demostrar el autoescalado.

QUÉ PROBLEMA RESUELVE

El autoescalado del documento reacciona a la CPU: sube una instancia cuando pasa del 70% durante
cinco minutos. Enseñar que funciona exige que la CPU suba de verdad y se quede arriba, y eso no
se consigue recargando el navegador.

POR QUÉ GOLPEA EL LOGIN Y NO EL CATÁLOGO

`/api/v1/courses` responde desde Redis: mil peticiones por segundo no moverían la CPU, porque el
trabajo lo hace otro servicio. El login, en cambio, verifica el hash de la contraseña, y ese
hash está diseñado para ser CARO a propósito — es lo que impide probar contraseñas por fuerza
bruta. Cada intento consume CPU de verdad, y es además el momento exacto que describe la sección
5 del documento: cinco mil estudiantes entrando a la vez cuando se abre la matrícula.

Usa las cuentas que siembra `app.infrastructure.seed`. No crea nada ni escribe en la base de
datos: solo autentica una y otra vez.

USO

    python deploy/azure/generar-carga.py --url http://matricula-xxxx.centralus.cloudapp.azure.com

    --hilos    peticiones en paralelo (40 por defecto)
    --minutos  cuánto mantener la carga (15 por defecto)

QUINCE MINUTOS NO ES UN CAPRICHO. La regla necesita cinco minutos por encima del umbral para
decidir, la instancia nueva tarda un par de minutos en arrancar el contenedor, y luego hay cinco
de espera antes de que el autoescalado vuelva a plantearse nada. Con menos, la gráfica se corta
justo antes de la parte interesante.
"""

from __future__ import annotations

import argparse
import json
import random
import ssl
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

PASSWORD = "SecurePass123"
CUENTAS = [f"estudiante{n:02d}@tdea.edu.co" for n in range(1, 51)]


@dataclass
class Contador:
    """Lo que va pasando, compartido entre todos los hilos."""

    exitos: int = 0
    fallos: int = 0
    latencias: list[float] = field(default_factory=list)
    candado: threading.Lock = field(default_factory=threading.Lock)

    def anotar(self, ok: bool, segundos: float) -> None:
        with self.candado:
            if ok:
                self.exitos += 1
                # Solo se guardan las últimas mil. Quince minutos a varios cientos por segundo
                # llenarían la memoria con datos que nadie va a mirar.
                self.latencias.append(segundos)
                if len(self.latencias) > 1000:
                    del self.latencias[:-1000]
            else:
                self.fallos += 1

    def leer_y_reiniciar(self) -> tuple[int, int, float]:
        with self.candado:
            e, f = self.exitos, self.fallos
            media = sum(self.latencias) / len(self.latencias) if self.latencias else 0.0
            self.exitos = self.fallos = 0
            return e, f, media


def un_login(url: str, contexto: ssl.SSLContext, contador: Contador) -> None:
    cuerpo = json.dumps(
        {"email": random.choice(CUENTAS), "password": PASSWORD}
    ).encode()
    peticion = urllib.request.Request(
        f"{url}/api/v1/auth/login",
        data=cuerpo,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    arranque = time.monotonic()
    try:
        with urllib.request.urlopen(peticion, timeout=30, context=contexto) as r:
            contador.anotar(r.status == 200, time.monotonic() - arranque)
    except urllib.error.HTTPError as e:
        # Un 429 NO es un fallo del sistema: es el limitador de peticiones haciendo su trabajo.
        # Se cuenta aparte para no ensuciar la lectura.
        contador.anotar(e.code == 429, time.monotonic() - arranque)
    except Exception:
        contador.anotar(False, time.monotonic() - arranque)


def martillear(url: str, hasta: float, contador: Contador, parar: threading.Event) -> None:
    contexto = ssl.create_default_context()
    while time.monotonic() < hasta and not parar.is_set():
        un_login(url, contexto, contador)


def main() -> None:
    p = argparse.ArgumentParser(description="Genera carga de CPU contra la API para ver el autoescalado.")
    p.add_argument("--url", required=True, help="Base de la API: la del gateway o la del App Service.")
    p.add_argument("--hilos", type=int, default=40)
    p.add_argument("--minutos", type=float, default=15.0)
    args = p.parse_args()

    url = args.url.rstrip("/")
    fin = time.monotonic() + args.minutos * 60
    contador = Contador()
    parar = threading.Event()

    print(f"Golpeando {url}/api/v1/auth/login")
    print(f"{args.hilos} hilos durante {args.minutos:g} minutos. Ctrl+C para cortar.\n")
    print(f"{'transcurrido':>12}  {'req/s':>8}  {'errores':>8}  {'latencia':>9}")

    hilos = [
        threading.Thread(target=martillear, args=(url, fin, contador, parar), daemon=True)
        for _ in range(args.hilos)
    ]
    for h in hilos:
        h.start()

    arranque = time.monotonic()
    try:
        while time.monotonic() < fin:
            time.sleep(15)
            ok, mal, media = contador.leer_y_reiniciar()
            transcurrido = int(time.monotonic() - arranque)
            print(
                f"{transcurrido // 60:>9}m{transcurrido % 60:02d}  "
                f"{ok / 15:>8.1f}  {mal:>8}  {media * 1000:>7.0f}ms"
            )
    except KeyboardInterrupt:
        print("\ncortado a mano")
    finally:
        parar.set()

    print("\nCarga terminada. La CPU tarda un par de minutos en bajar, y el autoescalado")
    print("otros diez en retirar instancias: la regla de bajada mira una ventana de 10 minutos.")


if __name__ == "__main__":
    main()
