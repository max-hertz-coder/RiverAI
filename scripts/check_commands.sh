#!/bin/bash

# Скрипт для проверки команд Telegram бота

BOT_TOKEN="8481562241:AAEbxXFq7IHKr1n5yckuyd_tuPO0thfuSI0"

echo "🤖 Проверка команд Telegram бота"
echo "🔧 Токен: ${BOT_TOKEN:0:10}..."
echo ""

# Проверяем текущие команды
echo "📋 Текущие команды бота:"
curl -s "https://api.telegram.org/bot$BOT_TOKEN/getMyCommands" | python3 -m json.tool

echo ""
echo "✅ Проверка завершена" 