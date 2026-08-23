"""Pruebas unitarias del adaptador de caché de Redis.

Comprueban lo que hace este adaptador *además* de hablar con Redis: no dejar que un fallo de
la caché tumbe una petición, y no dejar que una caída convierta cada petición en una espera.
Que Redis guarde y devuelva valores lo verifican los tests de integración.
"""

from __future__ import annotations

from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.infrastructure.cache.redis_cache_service import (
    _ESPERA_SEGUNDOS,
    _FALLOS_PARA_ABRIR,
    RedisCacheService,
)


class RedisFalso:
    """Doble del cliente de Redis con un interruptor de averías."""

    def __init__(self, *, falla: bool = False, error: type[Exception] = RedisConnectionError):
        self.falla = falla
        self._error = error
        self.datos: dict[str, str] = {}
        self.intentos = 0

    def _quizas_fallar(self) -> None:
        self.intentos += 1
        if self.falla:
            raise self._error("Redis no responde")

    def get(self, key: str) -> Any:
        self._quizas_fallar()
        return self.datos.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> Any:
        self._quizas_fallar()
        self.datos[key] = value
        return True

    def delete(self, *keys: str) -> Any:
        self._quizas_fallar()
        for k in keys:
            self.datos.pop(k, None)
        return len(keys)


def _adaptador(cliente: RedisFalso) -> RedisCacheService:
    return RedisCacheService(cliente)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Funcionamiento normal
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_returns_what_was_stored() -> None:
    cache = _adaptador(RedisFalso())

    cache.set("k", "valor", 30)

    assert cache.get("k") == "valor"


@pytest.mark.unit
def test_get_when_key_is_absent_returns_none() -> None:
    assert _adaptador(RedisFalso()).get("no-existe") is None


@pytest.mark.unit
def test_delete_removes_the_entry() -> None:
    cache = _adaptador(RedisFalso())
    cache.set("k", "valor", 30)

    cache.delete("k")

    assert cache.get("k") is None


@pytest.mark.unit
def test_set_passes_the_ttl_to_redis() -> None:
    registrado: dict[str, Any] = {}

    class Espia(RedisFalso):
        def set(self, key: str, value: str, ex: int | None = None) -> Any:
            registrado["ex"] = ex
            return super().set(key, value, ex)

    _adaptador(Espia()).set("k", "v", 45)

    assert registrado["ex"] == 45


@pytest.mark.unit
def test_get_ignores_a_value_that_is_not_text() -> None:
    # Cubre el caso de que alguien inyecte un cliente sin `decode_responses`: es preferible
    # tratar la entrada como ausente a devolver `bytes` donde el puerto promete `str`.
    cliente = RedisFalso()
    cliente.datos["k"] = b"bytes"  # type: ignore[assignment]

    assert _adaptador(cliente).get("k") is None


# ---------------------------------------------------------------------------
# Resiliencia: un fallo de la caché no puede tumbar la petición
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("error", [RedisConnectionError, RedisTimeoutError])
def test_get_when_redis_fails_returns_none_instead_of_raising(error: type[Exception]) -> None:
    assert _adaptador(RedisFalso(falla=True, error=error)).get("k") is None


@pytest.mark.unit
def test_set_when_redis_fails_does_not_raise() -> None:
    _adaptador(RedisFalso(falla=True)).set("k", "v", 30)


@pytest.mark.unit
def test_delete_when_redis_fails_does_not_raise() -> None:
    _adaptador(RedisFalso(falla=True)).delete("k")


@pytest.mark.unit
def test_a_programming_error_is_not_swallowed() -> None:
    """Solo se capturan los errores de Redis, nunca `Exception` a secas.

    Un `except Exception` escondería los defectos de programación detrás de la degradación de
    la caché, y el síntoma sería "el catálogo va lento" en vez de una traza que señala el bug.
    """

    class ClienteRoto(RedisFalso):
        def get(self, key: str) -> Any:
            raise AttributeError("defecto de programacion")

    with pytest.raises(AttributeError):
        _adaptador(ClienteRoto()).get("k")


# ---------------------------------------------------------------------------
# Cortacircuitos: una caída no puede costar un timeout por petición
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_circuit_opens_after_consecutive_failures_and_stops_calling_redis() -> None:
    # Sin esto, cada petición pagaría el `socket_connect_timeout` mientras Redis esté caído.
    # Con 5.000 estudiantes concurrentes, eso convierte una caché caída en una app caída.
    cliente = RedisFalso(falla=True)
    cache = _adaptador(cliente)

    for _ in range(_FALLOS_PARA_ABRIR):
        cache.get("k")

    assert cliente.intentos == _FALLOS_PARA_ABRIR

    # A partir de aquí ya no se intenta: se va directo a PostgreSQL.
    for _ in range(20):
        assert cache.get("k") is None

    assert (
        cliente.intentos == _FALLOS_PARA_ABRIR
    ), "se siguió llamando a Redis con el circuito abierto"


@pytest.mark.unit
def test_an_open_circuit_also_skips_writes_and_invalidations() -> None:
    cliente = RedisFalso(falla=True)
    cache = _adaptador(cliente)

    for _ in range(_FALLOS_PARA_ABRIR):
        cache.get("k")

    intentos_al_abrir = cliente.intentos
    cache.set("k", "v", 30)
    cache.delete("k")

    assert cliente.intentos == intentos_al_abrir


@pytest.mark.unit
def test_circuit_probes_again_after_the_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    reloj = {"ahora": 1_000.0}
    monkeypatch.setattr(
        "app.infrastructure.cache.redis_cache_service.time.monotonic",
        lambda: reloj["ahora"],
    )

    cliente = RedisFalso(falla=True)
    cache = _adaptador(cliente)

    for _ in range(_FALLOS_PARA_ABRIR):
        cache.get("k")

    intentos_al_abrir = cliente.intentos
    cache.get("k")
    assert cliente.intentos == intentos_al_abrir, "el circuito no llegó a abrirse"

    # Pasada la espera, se deja pasar una sonda.
    reloj["ahora"] += _ESPERA_SEGUNDOS + 0.1
    cache.get("k")

    assert cliente.intentos == intentos_al_abrir + 1


@pytest.mark.unit
def test_circuit_closes_when_redis_comes_back(monkeypatch: pytest.MonkeyPatch) -> None:
    reloj = {"ahora": 1_000.0}
    monkeypatch.setattr(
        "app.infrastructure.cache.redis_cache_service.time.monotonic",
        lambda: reloj["ahora"],
    )

    cliente = RedisFalso(falla=True)
    cache = _adaptador(cliente)

    for _ in range(_FALLOS_PARA_ABRIR):
        cache.get("k")

    # Redis vuelve, y la sonda posterior a la espera lo comprueba.
    cliente.falla = False
    reloj["ahora"] += _ESPERA_SEGUNDOS + 0.1
    cache.set("k", "recuperado", 30)

    # El circuito quedó cerrado: la caché vuelve a funcionar sin esperar nada más.
    assert cache.get("k") == "recuperado"


@pytest.mark.unit
def test_an_isolated_failure_does_not_open_the_circuit() -> None:
    # Un fallo suelto —un corte de red momentáneo— no debe desactivar la caché: solo lo hacen
    # los fallos CONSECUTIVOS.
    cliente = RedisFalso()
    cache = _adaptador(cliente)

    cliente.falla = True
    cache.get("k")
    cliente.falla = False
    cache.set("k", "v", 30)

    cliente.falla = True
    cache.get("k")
    cliente.falla = False

    assert cache.get("k") == "v"
