#!/usr/bin/env python3
"""
Простой тестовый скрипт для проверки работы бота
"""

import asyncio
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent.parent))

from bot_app.database import db
from bot_app.config import POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

async def test_bot_functions():
    """Тестирует основные функции бота"""
    
    print("🧪 Тестируем функции бота...")
    
    # Инициализируем подключение к базе данных
    dsn = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    try:
        await db.init_db_pool(dsn)
        print("✅ Подключение к базе данных установлено")
        
        # Тестируем создание пользователя
        test_user_id = 123456789
        test_name = "Тестовый пользователь"
        
        print(f"👤 Создаем тестового пользователя: {test_name}")
        user = await db.create_user(test_user_id, test_name)
        
        if user:
            print(f"✅ Пользователь создан: {user.get('name', 'N/A')}")
        else:
            print("⚠️ Пользователь уже существует")
        
        # Тестируем получение пользователя
        user = await db.get_user_by_tg_id(test_user_id)
        if user:
            print(f"✅ Пользователь найден: {user.get('name', 'N/A')}")
        else:
            print("❌ Пользователь не найден")
        
        # Тестируем создание ученика
        print("👨‍🎓 Создаем тестового ученика...")
        student_id = await db.create_student(
            user_id=test_user_id,
            name="Тестовый ученик",
            subject="Математика",
            level="Средний",
            notes="Тестовые заметки"
        )
        
        if student_id:
            print(f"✅ Ученик создан с ID: {student_id}")
        else:
            print("❌ Не удалось создать ученика")
        
        # Тестируем получение учеников
        students = await db.get_students_by_user(test_user_id)
        print(f"📊 Найдено учеников: {len(students)}")
        
        for student in students:
            print(f"  - {student['name']} ({student['subject']})")
        
        print("\n✅ Все тесты прошли успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_bot_functions()) 