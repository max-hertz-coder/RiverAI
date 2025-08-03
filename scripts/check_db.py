#!/usr/bin/env python3
"""
Скрипт для проверки подключения к базе данных
"""

import asyncio
import asyncpg
import os

# Конфигурация базы данных
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_NAME = os.getenv("DB_NAME", "riverai")

async def check_database():
    """Проверяет подключение к базе данных и структуру таблиц"""
    
    dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    try:
        print(f"🔍 Подключаемся к базе данных: {DB_HOST}:{DB_PORT}/{DB_NAME}")
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
        
        # Проверяем количество записей
        users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        students_count = await conn.fetchval("SELECT COUNT(*) FROM students")
        
        print(f"\n📊 Количество записей:")
        print(f"  - users: {users_count}")
        print(f"  - students: {students_count}")
        
        await conn.close()
        print("\n✅ Проверка завершена успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка при проверке базы данных: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(check_database()) 