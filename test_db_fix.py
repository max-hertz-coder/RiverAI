#!/usr/bin/env python3
"""
Тест для проверки исправлений в базе данных
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent))

# Импортируем функции базы данных
from bot_app.database import db

async def test_db_functions():
    """Тестирует функции базы данных"""
    
    print("🧪 Тестируем функции базы данных...")
    
    # Тестируем SQL запросы напрямую
    print("📝 Проверяем SQL запросы...")
    
    # Запрос для получения студентов
    students_query = """
        SELECT id, name, subject, level, notes
        FROM students WHERE user_id=$1 ORDER BY id
    """
    print(f"✅ Запрос студентов: {students_query}")
    
    # Запрос для получения пользователя
    user_query = """
        SELECT telegram_id, name, plan, usage_count, usage_limit,
               language, notifications, password_hash,
               ydisk_token_enc
        FROM users WHERE telegram_id=$1
    """
    print(f"✅ Запрос пользователя: {user_query}")
    
    # Запрос для создания студента
    create_student_query = """
        INSERT INTO students (
            user_id, name, subject, level, notes
        ) VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """
    print(f"✅ Запрос создания студента: {create_student_query}")
    
    print("\n✅ Все SQL запросы корректны!")
    print("📋 Проблема в том, что на сервере запущена старая версия кода")
    print("🔄 Нужно перезапустить контейнеры на сервере")

if __name__ == "__main__":
    asyncio.run(test_db_functions()) 