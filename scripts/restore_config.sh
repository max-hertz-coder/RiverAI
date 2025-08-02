#!/bin/bash

# Скрипт для восстановления правильной конфигурации после изменений друга
# Запускать на сервере

echo "🔧 Восстанавливаем правильную конфигурацию RiverAI..."

# 1. Останавливаем все контейнеры
echo "🛑 Останавливаем все контейнеры..."
docker-compose -f infrastructure/queue/docker-compose.yml down 2>/dev/null
docker-compose -f infrastructure/worker/docker-compose.yml down 2>/dev/null
docker-compose -f infrastructure/bot/docker-compose.yml down 2>/dev/null

# 2. Удаляем неправильную сеть
echo "🗑️ Удаляем неправильную сеть riverai-network..."
docker network rm riverai-network 2>/dev/null || echo "Сеть riverai-network не найдена"

# 3. Создаем правильную сеть
echo "📦 Создаем правильную сеть 'internal'..."
docker network create internal 2>/dev/null || echo "Сеть 'internal' уже существует"

# 4. Удаляем неправильные контейнеры если они есть
echo "🧹 Удаляем неправильные контейнеры..."
docker rm -f redis rabbitmq queue-server riverai-worker-1 2>/dev/null || echo "Контейнеры не найдены"

# 5. Восстанавливаем правильные .env файлы
echo "📝 Восстанавливаем .env файлы..."

# Определяем какой сервер (по наличию bot контейнера)
if docker ps -a | grep -q "bot-bot-1"; then
    echo "🔍 Обнаружен Сервер 2 (Bot)"
    # Это Сервер 2 - нужно подключение к внешним сервисам
    if [ -f ".env" ]; then
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
        # Нужно узнать IP Сервера 1
        echo "⚠️ На Сервере 2 нужно настроить .env файл с IP Сервера 1"
        echo "Замените в .env файле:"
        echo "RABBITMQ_HOST=queue-rabbitmq → RABBITMQ_HOST=<IP_СЕРВЕРА_1>"
        echo "REDIS_HOST=queue-redis → REDIS_HOST=<IP_СЕРВЕРА_1>"
    fi
else
    echo "🔍 Обнаружен Сервер 1 (Queue + Worker)"
    # Это Сервер 1 - локальные контейнеры
    if [ -f ".env" ]; then
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
        sed -i 's/RABBITMQ_HOST=.*/RABBITMQ_HOST=queue-rabbitmq/' .env
        sed -i 's/REDIS_HOST=.*/REDIS_HOST=queue-redis/' .env
        echo "✅ .env файл восстановлен для локальных контейнеров"
    fi
fi

# 6. Запускаем сервисы в правильном порядке
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

# Проверяем есть ли bot на этом сервере
if [ -d "../bot" ]; then
    echo "🚀 Запускаем bot..."
    cd ../bot
    docker-compose up -d
fi

echo "✅ Восстановление завершено!"

# 7. Проверяем статус
echo "🔍 Проверяем статус контейнеров..."
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "🔍 Проверяем сеть..."
docker network ls | grep internal

echo "🎉 Восстановление завершено!"
echo ""
echo "📋 Для проверки подключений:"
echo "docker exec riverai-worker-1 ping queue-rabbitmq"
echo "docker exec riverai-worker-1 ping queue-redis"
echo ""
echo "📋 Для просмотра логов:"
echo "docker logs riverai-worker-1"
echo "docker logs queue-server" 