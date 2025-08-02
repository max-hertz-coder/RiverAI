#!/bin/bash

# Скрипт для настройки Сервера 2 (Bot)
# Запускать на сервере с bot

echo "🔧 Настройка Сервера 2 (Bot)..."

# Проверяем аргумент
if [ -z "$1" ]; then
    echo "❌ Ошибка: Укажите IP адрес Сервера 1"
    echo "Использование: $0 <IP_СЕРВЕРА_1>"
    echo "Пример: $0 176.123.160.130"
    exit 1
fi

SERVER1_IP=$1

# 1. Останавливаем bot
echo "🛑 Останавливаем bot..."
docker-compose -f infrastructure/bot/docker-compose.yml down 2>/dev/null

# 2. Исправляем .env файл для внешних сервисов
echo "📝 Настраиваем .env файл для подключения к Серверу 1..."
if [ -f ".env" ]; then
    # Создаем резервную копию
    cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    
    # Настраиваем для внешних сервисов
    sed -i "s/RABBITMQ_HOST=.*/RABBITMQ_HOST=$SERVER1_IP/" .env
    sed -i "s/REDIS_HOST=.*/REDIS_HOST=$SERVER1_IP/" .env
    
    echo "✅ .env файл настроен для подключения к $SERVER1_IP"
else
    echo "❌ Файл .env не найден"
    exit 1
fi

# 3. Проверяем доступность сервисов
echo "🔍 Проверяем доступность сервисов на $SERVER1_IP..."
if nc -z $SERVER1_IP 5672; then
    echo "✅ RabbitMQ доступен на порту 5672"
else
    echo "❌ RabbitMQ недоступен на порту 5672"
    echo "Проверьте firewall и настройки на Сервере 1"
    exit 1
fi

if nc -z $SERVER1_IP 6379; then
    echo "✅ Redis доступен на порту 6379"
else
    echo "❌ Redis недоступен на порту 6379"
    echo "Проверьте firewall и настройки на Сервере 1"
    exit 1
fi

# 4. Запускаем bot
echo "🚀 Запускаем bot..."
cd infrastructure/bot
docker-compose up -d

echo "✅ Сервер 2 настроен!"

# 5. Проверяем статус
echo "🔍 Проверяем статус контейнеров..."
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo "🎉 Настройка Сервера 2 завершена!"
echo ""
echo "📋 Для проверки логов:"
echo "docker logs bot-bot-1"
echo ""
echo "📋 Для проверки подключений:"
echo "telnet $SERVER1_IP 5672"
echo "telnet $SERVER1_IP 6379" 