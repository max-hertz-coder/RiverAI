#!/bin/bash

# Скрипт для исправления конфигурации на сервере
# Запускать на удаленном сервере

echo "🔧 Исправляем конфигурацию RiverAI..."

# 1. Создаем Docker сеть если её нет
echo "📦 Создаем Docker сеть 'internal'..."
docker network create internal 2>/dev/null || echo "Сеть 'internal' уже существует"

# 2. Останавливаем все контейнеры
echo "🛑 Останавливаем все контейнеры..."
docker-compose -f infrastructure/queue/docker-compose.yml down 2>/dev/null
docker-compose -f infrastructure/worker/docker-compose.yml down 2>/dev/null
docker-compose -f infrastructure/bot/docker-compose.yml down 2>/dev/null

# 3. Исправляем .env файл
echo "📝 Исправляем .env файл..."
if [ -f ".env" ]; then
    # Создаем резервную копию
    cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    
    # Заменяем внешние IP на имена контейнеров
    sed -i 's/RABBITMQ_HOST=.*/RABBITMQ_HOST=queue-rabbitmq/' .env
    sed -i 's/REDIS_HOST=.*/REDIS_HOST=queue-redis/' .env
    
    echo "✅ .env файл исправлен"
else
    echo "❌ Файл .env не найден в текущей директории"
    exit 1
fi

# 4. Запускаем сервисы в правильном порядке
echo "🚀 Запускаем queue сервисы..."
cd infrastructure/queue
docker-compose up -d

echo "⏳ Ждем 10 секунд для инициализации..."
sleep 10

echo "🚀 Запускаем worker..."
cd ../worker
docker-compose up -d

echo "⏳ Ждем 5 секунд..."
sleep 5

echo "🚀 Запускаем bot..."
cd ../bot
docker-compose up -d

echo "✅ Все сервисы запущены!"

# 5. Проверяем статус
echo "🔍 Проверяем статус контейнеров..."
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "🔍 Проверяем сеть..."
docker network ls | grep internal

echo "🎉 Настройка завершена!"
echo ""
echo "📋 Для проверки подключений выполните:"
echo "docker exec riverai-worker-1 ping queue-rabbitmq"
echo "docker exec riverai-worker-1 ping queue-redis"
echo ""
echo "📋 Для просмотра логов:"
echo "docker logs riverai-worker-1"
echo "docker logs bot-bot-1" 