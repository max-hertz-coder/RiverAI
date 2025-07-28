# Используем официальный лёгкий образ Python
FROM python:3.10-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Сначала копируем файл зависимостей (для кэширования слоёв)
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Теперь копируем весь код репозитория в образ
# контекст сборки мы настроим ниже так, чтобы это было корневое /
COPY . .

# Гарантируем, что Python будет искать модули в /app
ENV PYTHONPATH=/app

# Точка входа — запускаем главный скрипт queue_server
CMD ["python", "queue_server/main.py"]
