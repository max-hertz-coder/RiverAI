# Инструкции по исправлению проблемы с базой данных

## Проблема
Ошибка `UndefinedColumnError: column "name_enc" does not exist` возникает из-за того, что в существующей базе данных отсутствуют необходимые колонки.

## Решение

### 1. Проверка текущего состояния базы данных
```bash
cd /path/to/RiverAI-1
python scripts/check_db.py
```

### 2. Выполнение миграции
```bash
python scripts/migrate_db.py
```

### 3. Повторная проверка
```bash
python scripts/check_db.py
```

## Что делает миграция

### Добавляемые колонки в таблицу `users`:
- `hide_disk_prompt` - флаг для скрытия напоминаний о Яндекс.Диске
- `tokens_prompt_total` - общее количество токенов промптов
- `tokens_gen_total` - общее количество токенов генерации
- `subscription_expires` - дата истечения подписки
- `trial_used` - флаг использования пробного периода
- `students_limit` - лимит учеников

### Добавляемые колонки в таблицу `students`:
- `usage_count` - количество использований
- `tokens_prompt_total` - общее количество токенов промптов
- `tokens_gen_total` - общее количество токенов генерации

## Альтернативное решение (если скрипты не работают)

### 1. Подключитесь к базе данных PostgreSQL:
```bash
psql -h localhost -U postgres -d riverai
```

### 2. Выполните SQL команды вручную:
```sql
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
```

### 3. Проверьте структуру таблиц:
```sql
-- Проверка таблицы users
\d users

-- Проверка таблицы students
\d students
```

## После исправления

После выполнения миграции бот должен работать корректно с новой системой нижнего меню. Все функции будут доступны через нижние кнопки:

- 👤 Ученики
- ➕ Добавить ученика  
- ⚙️ Настройки
- 💳 Подписка
- 📄 Учебный план
- 📝 Задания
- ✅ Проверить ДЗ
- 💬 Чат с GPT

## Проверка работы

1. Запустите бота
2. Отправьте команду `/start`
3. Проверьте, что нижнее меню отображается корректно
4. Попробуйте добавить ученика
5. Проверьте навигацию между разделами 