# bot_app/database/db.py
import asyncpg
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from bot_app.utils import encryption
from bot_app.utils.identity import hash_telegram_id

_pool: asyncpg.Pool | None = None


# ==============================
# Pool management
# ==============================
async def init_db_pool(dsn: str, **kwargs) -> None:
    """Создаёт пул подключений к PostgreSQL."""
    global _pool
    _pool = await asyncpg.create_pool(dsn, **kwargs)

def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized")
    return _pool


# ==============================
# Helpers
# ==============================
def _rec_to_dict(row: Optional[asyncpg.Record]) -> Optional[Dict[str, Any]]:
    return None if row is None else dict(row)

def _decrypt_or_empty(value: Optional[str]) -> str:
    return "" if not value else encryption.decrypt_str(value)


# ==============================
# Users
# ==============================
async def get_user_by_tg_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    """
    Возвращает пользователя. Добавлены поля consent_accepted_at, tutorial_asked, tutorial_shown.
    """
    pool = _get_pool()
    tg_hash = hash_telegram_id(telegram_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT telegram_hash, name_enc, plan, usage_count, usage_limit,
                   tokens_prompt_total, tokens_gen_total,
                   language, notifications, password_hash,
                   ydisk_token_enc, hide_disk_prompt,
                   subscription_expires, trial_used, students_limit,
                   consent_accepted_at, tutorial_asked, tutorial_shown
            FROM users
            WHERE telegram_hash = $1
            """,
            tg_hash,
        )
    data = _rec_to_dict(row)
    if not data:
        return None
    data["name"] = _decrypt_or_empty(data.get("name_enc"))
    return data

async def create_user(telegram_id: int, name: str) -> Dict[str, Any]:
    """Создаёт пользователя (trial 14 дней). Новые поля инициализируем как NULL/FALSE."""
    pool = _get_pool()
    name_enc = encryption.encrypt_str(name) if name else ""
    tg_hash = hash_telegram_id(telegram_id)
    now = datetime.now()
    trial_end = now + timedelta(days=14)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (
                telegram_hash, name_enc, plan, usage_count, usage_limit,
                tokens_prompt_total, tokens_gen_total,
                language, notifications, password_hash,
                ydisk_token_enc, hide_disk_prompt,
                subscription_expires, trial_used, students_limit,
                consent_accepted_at, tutorial_asked, tutorial_shown
            ) VALUES ($1,$2,'trial',0,200,0,0,'RU',true,'','',false,$3,false,1,
                      NULL,false,false)
            ON CONFLICT (telegram_hash) DO NOTHING
            """,
            tg_hash, name_enc, trial_end,
        )
    return (await get_user_by_tg_id(telegram_id)) or {}

async def has_user_consent(telegram_id: int) -> bool:
    tg_hash = hash_telegram_id(telegram_id)
    async with _get_pool().acquire() as conn:
        ts = await conn.fetchval("SELECT consent_accepted_at FROM users WHERE telegram_hash=$1", tg_hash)
    return bool(ts)

async def set_user_consent(telegram_id: int) -> None:
    tg_hash = hash_telegram_id(telegram_id)
    async with _get_pool().acquire() as conn:
        await conn.execute("UPDATE users SET consent_accepted_at = NOW() WHERE telegram_hash=$1", tg_hash)

async def has_tutorial_asked(telegram_id: int) -> bool:
    tg_hash = hash_telegram_id(telegram_id)
    async with _get_pool().acquire() as conn:
        v = await conn.fetchval("SELECT tutorial_asked FROM users WHERE telegram_hash=$1", tg_hash)
    return bool(v)

async def set_tutorial_asked(telegram_id: int) -> None:
    tg_hash = hash_telegram_id(telegram_id)
    async with _get_pool().acquire() as conn:
        await conn.execute("UPDATE users SET tutorial_asked = TRUE WHERE telegram_hash=$1", tg_hash)

async def set_tutorial_shown(telegram_id: int) -> None:
    """
    Помечаем, что видео уже показывали (используем при первом «Да»).
    Заодно фиксируем, что спрашивали.
    """
    tg_hash = hash_telegram_id(telegram_id)
    async with _get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET tutorial_shown = TRUE, tutorial_asked = TRUE WHERE telegram_hash=$1",
            tg_hash,
        )

async def update_user_name(user_id: int, new_name: str) -> None:
    tg_hash = hash_telegram_id(user_id)
    name_enc = encryption.encrypt_str(new_name)
    async with _get_pool().acquire() as conn:
        await conn.execute("UPDATE users SET name_enc=$1 WHERE telegram_hash=$2", name_enc, tg_hash)

async def update_user_password(user_id: int, new_password_hash: str) -> None:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        await conn.execute("UPDATE users SET password_hash=$1 WHERE telegram_hash=$2", new_password_hash, tg_hash)

async def update_user_language(user_id: int, new_lang: str) -> None:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        await conn.execute("UPDATE users SET language=$1 WHERE telegram_hash=$2", new_lang, tg_hash)

async def update_user_notifications(user_id: int, enabled: bool) -> None:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        await conn.execute("UPDATE users SET notifications=$1 WHERE telegram_hash=$2", enabled, tg_hash)

async def delete_user(user_id: int) -> None:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        await conn.execute("DELETE FROM users WHERE telegram_hash=$1", tg_hash)


# ==============================
# Students (как были)
# ==============================
async def get_students_by_user(user_id: int) -> List[Dict[str, Any]]:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, subject, grade, level, notes
            FROM students
            WHERE user_id=$1
            ORDER BY id
            """,
            tg_hash,
        )
    result: List[Dict[str, Any]] = []
    for r in rows:
        result.append({
            "id": r["id"],
            "name": _decrypt_or_empty(r["name"]),
            "subject": _decrypt_or_empty(r["subject"]),
            "level": _decrypt_or_empty(r["level"]),
            "grade": _decrypt_or_empty(r["grade"]) if r["grade"] else "",
            "notes": _decrypt_or_empty(r["notes"]) if r["notes"] else "",
        })
    return result

async def get_student(student_id: int) -> Optional[Dict[str, Any]]:
    async with _get_pool().acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM students WHERE id=$1", student_id)
    if not row:
        return None
    d = dict(row)
    return {
        "id": d["id"],
        "user_id": d["user_id"],
        "name": _decrypt_or_empty(d.get("name")),
        "subject": _decrypt_or_empty(d.get("subject")),
        "level": _decrypt_or_empty(d.get("level")),
        "grade": _decrypt_or_empty(d.get("grade")) if d.get("grade") else "",
        "notes": _decrypt_or_empty(d.get("notes")) if d.get("notes") else "",
        **{k: v for k, v in d.items() if k not in {"id", "user_id", "name", "subject", "grade", "level", "notes"}},
    }

async def add_student(user_id: int, name: str, subject: str, grade: str, level: str, notes: str) -> Optional[int]:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO students (user_id, name, subject, grade, level, notes)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            tg_hash,
            encryption.encrypt_str(name),
            encryption.encrypt_str(subject),
            encryption.encrypt_str(grade) if grade else "",
            encryption.encrypt_str(level),
            encryption.encrypt_str(notes) if notes else "",
        )
    return int(row["id"]) if row else None

async def update_student(
    student_id: int,
    name: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    level: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    sets: List[str] = []
    values: List[Any] = []
    if name is not None:
        sets.append(f"name=${len(values)+1}")
        values.append(encryption.encrypt_str(name))
    if subject is not None:
        sets.append(f"subject=${len(values)+1}")
        values.append(encryption.encrypt_str(subject))
    if grade is not None:
        sets.append(f"grade=${len(values)+1}")
        values.append(encryption.encrypt_str(grade) if grade else "")
    if level is not None:
        sets.append(f"level=${len(values)+1}")
        values.append(encryption.encrypt_str(level))
    if notes is not None:
        sets.append(f"notes=${len(values)+1}")
        values.append(encryption.encrypt_str(notes) if notes else "")
    if not sets:
        return
    values.append(student_id)
    sql = f"UPDATE students SET {', '.join(sets)} WHERE id=${len(values)}"
    async with _get_pool().acquire() as conn:
        await conn.execute(sql, *values)

async def delete_student(student_id: int) -> None:
    async with _get_pool().acquire() as conn:
        await conn.execute("DELETE FROM students WHERE id=$1", student_id)


# ==============================
# Usage & Stats (как были)
# ==============================
async def increment_usage(user_id: int) -> None:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        await conn.execute("UPDATE users SET usage_count = usage_count + 1 WHERE telegram_hash=$1", tg_hash)

async def increment_token_usage(user_id: int, prompt_tokens: int, gen_tokens: int) -> None:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE users SET
                tokens_prompt_total = tokens_prompt_total + $1,
                tokens_gen_total    = tokens_gen_total    + $2
            WHERE telegram_hash=$3
            """,
            int(prompt_tokens), int(gen_tokens), tg_hash
        )

async def increment_student_token_usage(student_id: int, prompt_tokens: int, gen_tokens: int) -> None:
    async with _get_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE students SET
                usage_count         = COALESCE(usage_count, 0) + 1,
                tokens_prompt_total = COALESCE(tokens_prompt_total, 0) + $1,
                tokens_gen_total    = COALESCE(tokens_gen_total, 0) + $2
            WHERE id=$3
            """,
            int(prompt_tokens), int(gen_tokens), student_id
        )

async def reset_usage(user_id: int) -> None:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        await conn.execute(
            "UPDATE users SET usage_count=0, tokens_prompt_total=0, tokens_gen_total=0 WHERE telegram_hash=$1",
            tg_hash,
        )

# ==============================
# Subscription / Plan (как были)
# ==============================
async def set_plan(user_id: int, plan: str, new_limit: Optional[int] = None) -> None:
    tg_hash = hash_telegram_id(user_id)
    limit = new_limit if new_limit is not None else (1000 if plan == "premium" else 200)
    async with _get_pool().acquire() as conn:
        await conn.execute("UPDATE users SET plan=$1, usage_limit=$2 WHERE telegram_hash=$3", plan, int(limit), tg_hash)

async def set_subscription(user_id: int, plan: str, students: int, until_date: datetime) -> None:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        await conn.execute(
            """
            UPDATE users
            SET plan=$1, students_limit=$2, subscription_expires=$3
            WHERE telegram_hash=$4
            """,
            plan, int(students), until_date, tg_hash
        )

async def has_active_subscription(user_id: int) -> bool:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        row = await conn.fetchval("SELECT subscription_expires FROM users WHERE telegram_hash=$1", tg_hash)
    if not row:
        return False
    try:
        return datetime.fromisoformat(str(row)) > datetime.now()
    except Exception:
        return False

async def mark_trial_used(user_id: int) -> None:
    tg_hash = hash_telegram_id(user_id)
    async with _get_pool().acquire() as conn:
        await conn.execute("UPDATE users SET trial_used=true WHERE telegram_hash=$1", tg_hash)

async def get_subscription_snapshot(user_id: int) -> Dict[str, Any]:
    u = await get_user_by_tg_id(user_id) or {}
    plan = (u.get("plan") or "standard").lower()
    students = int(u.get("students_limit") or 0)
    expires = u.get("subscription_expires")
    if isinstance(expires, str):
        try:
            expires = datetime.fromisoformat(expires)
        except Exception:
            expires = None
    is_paid_active = (plan != "trial") and (expires and expires > datetime.now())
    return {
        "plan": plan,
        "students_limit": students,
        "subscription_expires": expires,
        "is_paid_active": bool(is_paid_active),
    }
