import os
import asyncio
import asyncpg
from bot_app.utils.identity import hash_telegram_id

DB_HOST = os.environ.get("POSTGRES_HOST", "localhost")
DB_PORT = os.environ.get("POSTGRES_PORT", "5432")
DB_NAME = os.environ.get("POSTGRES_DB", "riverai_db")
DB_USER = os.environ.get("POSTGRES_USER", "riverai_user")
DB_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")

DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

async def migrate():
    print("📡 Connecting to DB...")
    conn = await asyncpg.connect(DSN)
    print("✅ Connected.")

    rows = await conn.fetch("SELECT id, telegram_id FROM users WHERE telegram_hash IS NULL")
    print(f"🔄 Updating {len(rows)} users...")

    for row in rows:
        tg_id = row["telegram_id"]
        if tg_id is None:
            continue
        tg_hash = hash_telegram_id(tg_id)
        await conn.execute("UPDATE users SET telegram_hash=$1 WHERE id=$2", tg_hash, row["id"])

    await conn.close()
    print("🎉 Migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate())
