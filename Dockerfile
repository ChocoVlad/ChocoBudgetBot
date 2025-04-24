# Используем лёгкий образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Указываем переменные окружения
ENV PYTHONUNBUFFERED=1

# Запускаем бота
CMD ["python", "main.py"]
