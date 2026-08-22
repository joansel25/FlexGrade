"""Suite de pruebas del backend, dividida en los tres niveles de la pirámide de tests.

- `unit`: dominio y casos de uso con dobles de test. Corren en milisegundos, sin red ni base de
  datos. Marca `unit`.
- `integration`: adaptadores contra infraestructura real levantada con Testcontainers
  (PostgreSQL, Redis). Marca `integration`.
- `e2e`: la API completa a través de un cliente HTTP. Marca `e2e`.

Las marcas se seleccionan con `pytest -m <marca>`. La pirámide se sostiene gracias a la
separación de capas: muchas pruebas unitarias, pocas end to end.
"""
