"""Pruebas end to end: la aplicación completa a través de peticiones HTTP.

Contiene hoy `test_health.py`. En las fases siguientes se sumarán los flujos completos de
usuario: login y consulta de un endpoint protegido, consulta del catálogo, inscripción y
cancelación, y autorización por rol.

Verifican el contrato público de la API tal como lo ve un cliente, no los detalles internos.
Son las más lentas y las menos numerosas. Se marcan con `@pytest.mark.e2e`.
"""
