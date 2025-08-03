#!/usr/bin/env python3
"""
Простой скрипт для тестирования подключения к базе данных
"""

import asyncio
import asyncpg
import os
from pathlib import Path

# Добавляем путь к проекту для импорта конфигурации
import sys
sys.path.append(str(Path(__file__).parent.parent))

# Импортируем конфигурацию
from bot_app.config import POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

async def test_connection():
    """Тестирует подключение к базе данных"""
    
    print(f"🔍 Тестируем подключение к: {POSTGRES_HOST}:{POSTGRES_PORT}")
    print(f"👤 Пользователь: {POSTGRES_USER}")
    print(f"📁 База данных: {POSTGRES_DB}")
    
    dsn = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    try:
        print("🔄 Подключаемся...")
        conn = await asyncpg.connect(dsn, timeout=10)
        print("✅ Подключение успешно!")
        
        # Простая проверка
        result = await conn.fetchval("SELECT 1")
        print(f"✅ Тестовый запрос выполнен: {result}")
        
        # Проверяем таблицы
        tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        print(f"📊 Найдено таблиц: {len(tables)}")
        for table in tables:
            print(f"  - {table['table_name']}")
        
        await conn.close()
        print("✅ Тест завершен успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        print(f"🔧 Тип ошибки: {type(e).__name__}")

if __name__ == "__main__":
    asyncio.run(test_connection()) 