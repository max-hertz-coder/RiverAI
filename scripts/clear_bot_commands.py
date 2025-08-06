#!/usr/bin/env python3
"""
Скрипт для очистки команд бота и установки только /start и /help
"""

import asyncio
import os
import sys
import ssl
from dotenv import load_dotenv
import aiohttp

# Загружаем переменные окружения
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN не найден в переменных окружения")
    sys.exit(1)

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Создаем SSL контекст без проверки сертификатов
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

async def delete_my_commands():
    """Удаляет все команды бота"""
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Удаляем команды без указания scope
        url = f"{BASE_URL}/deleteMyCommands"
        
        async with session.post(url) as response:
            result = await response.json()
            if result.get("ok"):
                print("✅ Удалены все команды бота")
            else:
                print(f"⚠️ Не удалось удалить команды: {result}")

async def set_my_commands():
    """Устанавливает только команды /start и /help"""
    commands = [
        {"command": "start", "description": "Старт бота"},
        {"command": "help", "description": "Помощь"}
    ]
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Устанавливаем команды для русского языка
        url = f"{BASE_URL}/setMyCommands"
        data = {
            "commands": commands,
            "language_code": "ru"
        }
        
        async with session.post(url, json=data) as response:
            result = await response.json()
            if result.get("ok"):
                print("✅ Установлены команды для русского языка")
            else:
                print(f"❌ Ошибка установки команд для русского языка: {result}")
        
        # Устанавливаем команды для английского языка
        commands_en = [
            {"command": "start", "description": "Start bot"},
            {"command": "help", "description": "Help"}
        ]
        
        data = {
            "commands": commands_en,
            "language_code": "en"
        }
        
        async with session.post(url, json=data) as response:
            result = await response.json()
            if result.get("ok"):
                print("✅ Установлены команды для английского языка")
            else:
                print(f"❌ Ошибка установки команд для английского языка: {result}")

async def get_my_commands():
    """Показывает текущие команды бота"""
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        url = f"{BASE_URL}/getMyCommands"
        
        async with session.post(url) as response:
            result = await response.json()
            if result.get("ok"):
                commands = result.get("result", [])
                if commands:
                    print("📋 Текущие команды бота:")
                    for cmd in commands:
                        print(f"  /{cmd['command']} - {cmd['description']}")
                else:
                    print("📋 Команды бота не установлены")
            else:
                print(f"❌ Ошибка получения команд: {result}")

async def main():
    print("🤖 Очистка команд Telegram бота")
    print(f"🔧 Токен: {BOT_TOKEN[:10]}...")
    print()
    
    # Показываем текущие команды
    print("📋 Проверяем текущие команды...")
    await get_my_commands()
    print()
    
    # Удаляем все команды
    print("🗑️ Удаляем все команды...")
    await delete_my_commands()
    print()
    
    # Устанавливаем новые команды
    print("✅ Устанавливаем команды /start и /help...")
    await set_my_commands()
    print()
    
    # Показываем результат
    print("📋 Проверяем результат...")
    await get_my_commands()
    print()
    print("🎉 Готово! Команды обновлены.")

if __name__ == "__main__":
    asyncio.run(main()) 