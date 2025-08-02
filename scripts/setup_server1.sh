#!/bin/bash

# Скрипт для настройки Сервера 1 (Queue + Worker)
# Запускать на сервере с queue и worker

echo "🔧 Настройка Сервера 1 (Queue + Worker)..."

# 1. Создаем Docker сеть
echo "📦 Создаем Docker сеть 'internal'..."
docker network create internal 2>/dev/null || echo "Сеть 'internal' уже существует"

# 2. Останавливаем контейнеры
echo "🛑 Останавливаем контейнеры..."
docker-compose -f infrastructure/queue/docker-compose.yml down 2>/dev/null
docker-compose -f infrastructure/worker/docker-compose.yml down 2>/dev/null

# 3. Исправляем .env файл для локальных контейнеров
echo "📝 Настраиваем .env файл..."
if [ -f ".env" ]; then
    # Создаем резервную копию
    cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    
    # Настраиваем для локальных контейнеров
    sed -i 's/RABBITMQ_HOST=.*/RABBITMQ_HOST=queue-rabbitmq/' .env
    sed -i 's/REDIS_HOST=.*/REDIS_HOST=queue-redis/' .env
    
    echo "✅ .env файл настроен для локальных контейнеров"
else
    echo "❌ Файл .env не найден"
    exit 1
fi

# 4. Запускаем queue сервисы
echo "🚀 Запускаем queue сервисы..."
cd infrastructure/queue
docker-compose up -d

echo "⏳ Ждем 10 секунд для инициализации..."
sleep 10

# 5. Запускаем worker
echo "🚀 Запускаем worker..."
cd ../worker
docker-compose up -d

echo "✅ Сервер 1 настроен!"

# 6. Проверяем статус
echo "🔍 Проверяем статус контейнеров..."
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "🎉 Настройка Сервера 1 завершена!"
echo ""
echo "📋 IP адрес этого сервера для настройки Сервера 2:"
echo "$(curl -s ifconfig.me || hostname -I | awk '{print $1}')"
echo ""
echo "📋 Для проверки подключений:"
echo "docker exec riverai-worker-1 ping queue-rabbitmq"
echo "docker exec riverai-worker-1 ping queue-redis" 