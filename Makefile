.PHONY: start stop migrate-up migrate-down

start:
	docker compose up -d --build

stop:
	docker compose down

migrate-up:
	docker compose run --rm bot sh -c 'bash ./migrate.sh up'

migrate-down:
	docker compose run --rm bot sh -c 'bash ./migrate.sh down'
