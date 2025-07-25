FROM python:3.10-slim

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Копируем весь проект внутрь контейнера
COPY . .

# Указываем корень PYTHONPATH — чтобы bot_app стал виден
ENV PYTHONPATH=/app

CMD ["python", "queue_server/main.py"]
