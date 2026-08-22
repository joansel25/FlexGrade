"""Configuración de la aplicación.

Contiene `settings.py`, donde se declara la clase `Settings` (Pydantic Settings) con las
variables de entorno del backend y la función `get_settings()` que la expone cacheada.

Es el único punto del código que lee del entorno: ningún otro módulo llama a `os.environ`. Los
secretos viven en variables de entorno, nunca en el repositorio.
"""
