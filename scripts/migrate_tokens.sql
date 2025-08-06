-- Скрипт миграции для добавления полей подсчета токенов
-- Выполните этот скрипт в вашей базе данных

-- Добавляем поля для подсчета токенов в таблицу users
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS tokens_prompt_total BIGINT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS tokens_gen_total BIGINT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS hide_disk_prompt BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS subscription_expires TIMESTAMP,
ADD COLUMN IF NOT EXISTS trial_used BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS students_limit INT NOT NULL DEFAULT 1;

-- Добавляем поля для подсчета токенов в таблицу students
ALTER TABLE students 
ADD COLUMN IF NOT EXISTS usage_count INT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS tokens_prompt_total BIGINT NOT NULL DEFAULT 0,
ADD COLUMN IF NOT EXISTS tokens_gen_total BIGINT NOT NULL DEFAULT 0;

-- Создаем индексы для быстрого поиска по токенам
CREATE INDEX IF NOT EXISTS idx_users_tokens ON users(tokens_prompt_total, tokens_gen_total);
CREATE INDEX IF NOT EXISTS idx_students_tokens ON students(tokens_prompt_total, tokens_gen_total);

-- Выводим информацию о миграции
SELECT 'Миграция завершена успешно' as status; 