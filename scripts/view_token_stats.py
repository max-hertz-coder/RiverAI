#!/usr/bin/env python3
"""
Скрипт для просмотра статистики токенов пользователей
"""

import asyncio
import asyncpg
from dotenv import load_dotenv
import os

load_dotenv()

# Конфигурация БД
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
DB_NAME = os.getenv("POSTGRES_DB", "riverai_db")
DB_USER = os.getenv("POSTGRES_USER", "riverai_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")

async def get_token_stats():
    """Получает статистику токенов из БД"""
    dsn = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    try:
        conn = await asyncpg.connect(dsn)
        
        # Статистика пользователей
        print("📊 СТАТИСТИКА ТОКЕНОВ ПОЛЬЗОВАТЕЛЕЙ")
        print("=" * 50)
        
        users_stats = await conn.fetch("""
            SELECT 
                telegram_id,
                usage_count,
                tokens_prompt_total,
                tokens_gen_total,
                (tokens_prompt_total + tokens_gen_total) as total_tokens
            FROM users 
            WHERE tokens_prompt_total > 0 OR tokens_gen_total > 0
            ORDER BY total_tokens DESC
            LIMIT 10
        """)
        
        if users_stats:
            print(f"{'ID':<12} {'Использований':<15} {'Prompt токены':<15} {'Gen токены':<15} {'Всего токенов':<15}")
            print("-" * 75)
            for user in users_stats:
                print(f"{user['telegram_id']:<12} {user['usage_count']:<15} {user['tokens_prompt_total']:<15} {user['tokens_gen_total']:<15} {user['total_tokens']:<15}")
        else:
            print("Нет данных о токенах пользователей")
        
        print("\n" + "=" * 50)
        
        # Статистика учеников
        print("📊 СТАТИСТИКА ТОКЕНОВ УЧЕНИКОВ")
        print("=" * 50)
        
        students_stats = await conn.fetch("""
            SELECT 
                s.id,
                s.user_id,
                s.usage_count,
                s.tokens_prompt_total,
                s.tokens_gen_total,
                (s.tokens_prompt_total + s.tokens_gen_total) as total_tokens
            FROM students s
            WHERE s.tokens_prompt_total > 0 OR s.tokens_gen_total > 0
            ORDER BY total_tokens DESC
            LIMIT 10
        """)
        
        if students_stats:
            print(f"{'ID ученика':<12} {'ID пользователя':<15} {'Использований':<15} {'Prompt токены':<15} {'Gen токены':<15} {'Всего токенов':<15}")
            print("-" * 90)
            for student in students_stats:
                print(f"{student['id']:<12} {student['user_id']:<15} {student['usage_count']:<15} {student['tokens_prompt_total']:<15} {student['tokens_gen_total']:<15} {student['total_tokens']:<15}")
        else:
            print("Нет данных о токенах учеников")
        
        # Общая статистика
        print("\n" + "=" * 50)
        print("📊 ОБЩАЯ СТАТИСТИКА")
        print("=" * 50)
        
        total_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_users,
                SUM(usage_count) as total_usage,
                SUM(tokens_prompt_total) as total_prompt_tokens,
                SUM(tokens_gen_total) as total_gen_tokens,
                SUM(tokens_prompt_total + tokens_gen_total) as total_tokens
            FROM users
        """)
        
        if total_stats:
            print(f"Всего пользователей: {total_stats['total_users']}")
            print(f"Всего использований: {total_stats['total_usage']}")
            print(f"Всего prompt токенов: {total_stats['total_prompt_tokens']:,}")
            print(f"Всего gen токенов: {total_stats['total_gen_tokens']:,}")
            print(f"Всего токенов: {total_stats['total_tokens']:,}")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")

async def main():
    print("🔍 Просмотр статистики токенов")
    print(f"🔧 Подключение к БД: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    print()
    
    await get_token_stats()

if __name__ == "__main__":
    asyncio.run(main()) 