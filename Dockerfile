FROM python:3.11

WORKDIR /app

# Установим psql
RUN apt-get update && apt-get install -y postgresql-client

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py"]
