# Comandos del dia a dia del Sistema de Matricula.
# Ver DEVELOPMENT_WORKFLOW.md seccion 12 y CI_CD.md seccion 11.
#
# Todo corre dentro de los contenedores: no hace falta tener Python, Postgres ni
# Redis instalados en la maquina, solo Docker.
#
# Si tu instalacion usa el binario antiguo v1, invoca:  make COMPOSE=docker-compose <target>

COMPOSE ?= docker compose
BACKEND_IMAGE ?= matricula-backend:local

.PHONY: dev build test test-unit test-int test-e2e lint format migrate migrate-create seed clean

## Levanta postgres + redis + backend (el backend espera a que los datos esten sanos)
dev:
	$(COMPOSE) up -d --build
	@echo "Backend en http://localhost:8000  |  health: http://localhost:8000/health"

## Construye la imagen de produccion del backend (misma que valida el CI)
build:
	docker build -t $(BACKEND_IMAGE) ./backend

## Toda la suite de tests
test:
	$(COMPOSE) exec backend pytest

## Solo tests unitarios (rapidos, sin IO)
#
# Se ejecutan con una DATABASE_URL y una REDIS_URL DELIBERADAMENTE INALCANZABLES. No es un
# adorno: un test unitario que necesite infraestructura deja de serlo, y dentro del contenedor
# Postgres y Redis siempre estan a mano, asi que esa dependencia se cuela sin que nadie lo
# note. El CI corre este paso sin ningun servicio y ahi si falla, pero descubrirlo alli cuesta
# una vuelta entera de pipeline. Con estos valores, el mismo fallo aparece al instante en local.
test-unit:
	$(COMPOSE) exec \
	  -e DATABASE_URL=postgresql+psycopg://nadie:nadie@sin-base-de-datos:5432/ninguna \
	  -e REDIS_URL=redis://sin-cache:6379/0 \
	  backend pytest -m unit

## Solo tests de integracion (tocan base de datos y cache)
test-int:
	$(COMPOSE) exec backend pytest -m integration

## Solo tests e2e (en proceso, contra la app con TestClient)
test-e2e:
	$(COMPOSE) exec backend pytest -m e2e

## Verifica formato y tipos sin modificar nada (lo mismo que corre el CI)
lint:
	$(COMPOSE) exec backend black --check app tests
	$(COMPOSE) exec backend isort --check-only app tests
	$(COMPOSE) exec backend mypy app

## Aplica formato automatico
format:
	$(COMPOSE) exec backend black app tests
	$(COMPOSE) exec backend isort app tests

## Aplica las migraciones pendientes
migrate:
	$(COMPOSE) exec backend alembic upgrade head

## Crea una migracion nueva:  make migrate-create msg="agrega tabla enrollments"
migrate-create:
	@test -n "$(msg)" || { echo 'Falta el mensaje. Uso: make migrate-create msg="descripcion"'; exit 1; }
	$(COMPOSE) exec backend alembic revision --autogenerate -m "$(msg)"

## Carga datos de ejemplo (idempotente)
seed:
	$(COMPOSE) exec backend python -m app.infrastructure.seed

## Baja todo y BORRA los volumenes de datos (postgres y redis quedan vacios)
clean:
	$(COMPOSE) down -v
