-- db_server/init_db.sql
-- Начальная схема для бота RiverAI

-- Таблица пользователей
CREATE TABLE IF NOT EXISTS users (
    telegram_id   BIGINT        PRIMARY KEY,
    name_enc      TEXT,
    plan          VARCHAR(50)   NOT NULL DEFAULT 'basic',
    usage_count   INT           NOT NULL DEFAULT 0,
    usage_limit   INT           NOT NULL DEFAULT 0,
    language      VARCHAR(5)    NOT NULL DEFAULT 'RU',
    notifications BOOLEAN      NOT NULL DEFAULT TRUE,
    password_hash TEXT          NOT NULL DEFAULT '',
    ydisk_token_enc TEXT         NOT NULL DEFAULT ''
);

-- Таблица учеников
CREATE TABLE IF NOT EXISTS students (
    id           SERIAL       PRIMARY KEY,
    user_id      BIGINT       NOT NULL
        REFERENCES users(telegram_id)
        ON DELETE CASCADE,
    name_enc     TEXT         NOT NULL,
    subject_enc  TEXT         NOT NULL,
    level_enc    TEXT         NOT NULL,
    notes_enc    TEXT
);

-- Индекс для быстрого поиска учеников по пользователю
CREATE INDEX IF NOT EXISTS idx_students_user_id
    ON students(user_id);
