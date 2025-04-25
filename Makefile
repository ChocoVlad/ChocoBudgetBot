.PHONY: start stop restart migrate-up migrate-down migrate-up-one migrate-down-one

start:
	docker compose up -d --build

stop:
	docker compose down

restart:
	make stop
	make start

migrate-up:
	docker compose run --rm bot sh -c "bash ./migrate.sh up"

migrate-down:
	docker compose run --rm bot sh -c "bash ./migrate.sh down"

migrate-up-one:
	docker compose run --rm bot sh -c "goose -dir ./migrations -table migrations_applied up-by-one"

migrate-down-one:
	docker compose run --rm bot sh -c "goose -dir ./migrations -table migrations_applied down"
