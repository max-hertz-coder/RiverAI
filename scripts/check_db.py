#!/usr/bin/env python3
"""
Скрипт для проверки подключения к базе данных
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

async def check_database():
    """Проверяет подключение к базе данных и структуру таблиц"""
    
    dsn = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    try:
        print(f"🔍 Подключаемся к базе данных: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
        print(f"👤 Пользователь: {POSTGRES_USER}")
        conn = await asyncpg.connect(dsn)
        print("✅ Подключение успешно!")
        
        # Проверяем существование таблиц
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        print(f"\n📊 Найденные таблицы: {[t['table_name'] for t in tables]}")
        
        # Проверяем структуру таблицы users
        if any(t['table_name'] == 'users' for t in tables):
            print("\n📋 Структура таблицы users:")
            users_columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                ORDER BY ordinal_position
            """)
            
            for col in users_columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                print(f"  - {col['column_name']}: {col['data_type']} {nullable}")
        else:
            print("\n❌ Таблица 'users' не найдена!")
        
        # Проверяем структуру таблицы students
        if any(t['table_name'] == 'students' for t in tables):
            print("\n📋 Структура таблицы students:")
            students_columns = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'students' 
                ORDER BY ordinal_position
            """)
            
            for col in students_columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                print(f"  - {col['column_name']}: {col['data_type']} {nullable}")
        else:
            print("\n❌ Таблица 'students' не найдена!")
        
        # Проверяем количество записей
        try:
            users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            print(f"\n📊 Количество записей в users: {users_count}")
        except Exception as e:
            print(f"\n❌ Ошибка при подсчете записей в users: {e}")
        
        try:
            students_count = await conn.fetchval("SELECT COUNT(*) FROM students")
            print(f"📊 Количество записей в students: {students_count}")
        except Exception as e:
            print(f"❌ Ошибка при подсчете записей в students: {e}")
        
        await conn.close()
        print("\n✅ Проверка завершена успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке базы данных: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(check_database()) 