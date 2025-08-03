#!/usr/bin/env python3
"""
Скрипт для миграции базы данных
Добавляет недостающие колонки в существующую базу данных
"""

import asyncio
import asyncpg
import os
from pathlib import Path

# Конфигурация базы данных
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_NAME = os.getenv("DB_NAME", "riverai")

async def run_migration():
    """Запускает миграцию базы данных"""
    
    # Подключаемся к базе данных
    dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    try:
        conn = await asyncpg.connect(dsn)
        print("✅ Подключились к базе данных")
        
        # Читаем файл миграции
        migration_file = Path(__file__).parent.parent / "db_server" / "migrate_db.sql"
        
        if not migration_file.exists():
            print(f"❌ Файл миграции не найден: {migration_file}")
            return
        
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        print("📄 Выполняем миграцию...")
        
        # Выполняем миграцию
        await conn.execute(migration_sql)
        
        print("✅ Миграция успешно выполнена!")
        
        # Проверяем структуру таблиц
        print("\n📊 Проверяем структуру таблиц:")
        
        # Проверяем таблицу users
        users_columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'users' 
            ORDER BY ordinal_position
        """)
        
        print("\nТаблица users:")
        for col in users_columns:
            print(f"  - {col['column_name']}: {col['data_type']} {'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'}")
        
        # Проверяем таблицу students
        students_columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'students' 
            ORDER BY ordinal_position
        """)
        
        print("\nТаблица students:")
        for col in students_columns:
            print(f"  - {col['column_name']}: {col['data_type']} {'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'}")
        
        await conn.close()
        print("\n✅ Миграция завершена успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка при выполнении миграции: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(run_migration()) 