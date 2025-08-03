-- db_server/migrate_db.sql
-- Миграция для добавления недостающих колонок

-- Добавляем недостающие колонки в таблицу users
ALTER TABLE users ADD COLUMN IF NOT EXISTS hide_disk_prompt BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_prompt_total INT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS tokens_gen_total INT NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_expires TIMESTAMP;
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_used BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS students_limit INT NOT NULL DEFAULT 3;

-- Добавляем недостающие колонки в таблицу students
ALTER TABLE students ADD COLUMN IF NOT EXISTS usage_count INT NOT NULL DEFAULT 0;
ALTER TABLE students ADD COLUMN IF NOT EXISTS tokens_prompt_total INT NOT NULL DEFAULT 0;
ALTER TABLE students ADD COLUMN IF NOT EXISTS tokens_gen_total INT NOT NULL DEFAULT 0;

-- Обновляем существующие записи
UPDATE users SET 
    hide_disk_prompt = FALSE,
    tokens_prompt_total = 0,
    tokens_gen_total = 0,
    trial_used = FALSE,
    students_limit = 3
WHERE hide_disk_prompt IS NULL 
   OR tokens_prompt_total IS NULL 
   OR tokens_gen_total IS NULL 
   OR trial_used IS NULL 
   OR students_limit IS NULL;

UPDATE students SET 
    usage_count = 0,
    tokens_prompt_total = 0,
    tokens_gen_total = 0
WHERE usage_count IS NULL 
   OR tokens_prompt_total IS NULL 
   OR tokens_gen_total IS NULL; 