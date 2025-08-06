#!/bin/bash

# Скрипт для проверки команд Telegram бота

# Загружаем переменные окружения
source .env 2>/dev/null || echo "⚠️ Файл .env не найден"

BOT_TOKEN=${BOT_TOKEN}
if [ -z "$BOT_TOKEN" ]; then
    echo "❌ BOT_TOKEN не найден в переменных окружения"
    exit 1
fi

echo "🤖 Проверка команд Telegram бота"
echo "🔧 Токен: ${BOT_TOKEN:0:10}..."
echo ""

# Проверяем текущие команды
echo "📋 Текущие команды бота:"
curl -s "https://api.telegram.org/bot$BOT_TOKEN/getMyCommands" | python3 -m json.tool

echo ""
echo "✅ Проверка завершена" 