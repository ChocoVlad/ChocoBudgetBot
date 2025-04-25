import time
import sqlite3
import os

DB_PATH = "data/bot.db"

print("Ожидаем доступность БД...")

for _ in range(30):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1;")
        conn.close()
        print("БД доступна")
        break
    except Exception as e:
        print(f"БД ещё не доступна: {e}")
        time.sleep(1)
else:
    raise RuntimeError("База данных недоступна после 30 попыток")
