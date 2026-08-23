"""Pruebas del cableado de dependencias.

Comprueban el CICLO DE VIDA de lo que construye `di.py`, no su comportamiento. Es una
distinción sutil y cara de aprender: el adaptador de caché puede estar perfectamente
implementado y probado y aun así no funcionar en producción si el contenedor lo reconstruye en
cada petición y descarta su estado. Eso ocurrió de verdad al implementar el cortacircuitos,
y estos tests son la red que impide que vuelva a ocurrir.
"""

from __future__ import annotations

import pytest

from app.interfaces.api.dependencies.di import get_cache_service


@pytest.mark.unit
def test_cache_service_is_a_singleton_so_the_circuit_breaker_survives() -> None:
    """El adaptador de caché tiene que ser el mismo entre peticiones.

    Lleva dentro el cortacircuitos que desactiva Redis tras varios fallos seguidos. Si cada
    petición construyera uno nuevo, el contador de fallos volvería a cero antes de alcanzar el
    umbral y el circuito no se abriría jamás: durante una caída de Redis, cada una de las
    5.000 peticiones concurrentes pagaría el tiempo de espera completo.

    El síntoma en producción sería «el catálogo va lentísimo cuando Redis falla», con todos
    los tests del adaptador en verde, porque en ellos la instancia sí se reutiliza.
    """
    assert get_cache_service() is get_cache_service()
