"""Configuración del backend leída de variables de entorno.

Este módulo es el único punto del código que lee del entorno. Los atributos usan `snake_case`
(convención de `BEST_PRACTICES.md` secciones 1 y 10) y Pydantic Settings los resuelve contra las
variables de entorno en mayúsculas sin distinguir caso: `database_url` se alimenta de
`DATABASE_URL`, y así con el resto.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parámetros de ejecución de la aplicación.

    Las variables sin valor por defecto son obligatorias: si faltan, la aplicación falla al
    arrancar con un error explícito en vez de comportarse de forma impredecible en caliente.

    Attributes:
        database_url: DSN de PostgreSQL, en formato SQLAlchemy 2.x
            (ej. `postgresql+psycopg://usuario:clave@host:5432/base`). Obligatorio.
        redis_url: URL del servidor Redis usado como caché del catálogo. Obligatorio.
        jwt_secret: secreto de firma de los tokens. Obligatorio; nunca se versiona.
        jwt_expiration_seconds: vigencia del token de acceso, en segundos.
        jwt_refresh_expiration_seconds: vigencia del token de refresco, en segundos.
        environment: ambiente de ejecución (`dev`, `staging`, `prod`).
        log_level: nivel mínimo de logging (`DEBUG`, `INFO`, `WARNING`, `ERROR`).
        api_v1_prefix: prefijo común de los endpoints de negocio de la versión 1.
        app_version: versión de la aplicación que se reporta en `/health` y en OpenAPI.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    redis_url: str
    jwt_secret: str
    jwt_expiration_seconds: int = 3600
    jwt_refresh_expiration_seconds: int = 604800
    environment: str = "dev"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    app_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración de la aplicación, resuelta una sola vez.

    El resultado se cachea porque la configuración es inmutable durante la vida del proceso:
    así se evita releer el entorno en cada request y se obtiene una única instancia compartida,
    apta para inyectarse como dependencia de FastAPI.

    Returns:
        Settings: la configuración validada a partir del entorno.
    """
    # Se construye sin argumentos a propósito: Pydantic Settings toma los valores del entorno.
    return Settings()
