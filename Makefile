.PHONY: start stop restart migrate-up migrate-down

start:
	docker compose up -d --build

stop:
	docker compose down

restart:
	make stop
	make start

migrate-up:
	docker compose exec db bash -c "PGPASSWORD=bot_password bash /app/migrate.sh up"

migrate-down:
	docker compose exec db bash -c "PGPASSWORD=bot_password bash /app/migrate.sh down"
