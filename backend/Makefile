.PHONY: dev test lint fmt migrate upgrade

dev:
	docker-compose up --build

test:
	docker-compose exec -T api alembic upgrade head
	docker-compose exec -T api pytest

lint:
	ruff check .
	mypy app

fmt:
	black .
	ruff check . --fix

migrate:
	alembic revision --autogenerate -m "migration"

upgrade:
	alembic upgrade head
