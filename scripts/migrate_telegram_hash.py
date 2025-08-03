import os
import asyncio
import asyncpg

try:
    from bot_app.utils.identity import hash_telegram_id
except ImportError:
    from worker.utils.identity import hash_telegram_id

DSN = os.getenv("WORKER_POSTGRES_DSN") or os.getenv("POSTGRES_DSN")
if not DSN:
    raise RuntimeError("❌ DSN not provided — set WORKER_POSTGRES_DSN or POSTGRES_DSN")

async def migrate():
    print("📡 Connecting to DB...")
    conn = await asyncpg.connect(DSN)
    print("✅ Connected.")

    rows = await conn.fetch("SELECT telegram_id FROM users WHERE telegram_hash IS NULL")
    print(f"🔄 Updating {len(rows)} users...")

    updated = 0
    for row in rows:
        tg_id = row["telegram_id"]
        if tg_id is None:
            continue
        tg_hash = hash_telegram_id(tg_id)
        await conn.execute("UPDATE users SET telegram_hash=$1 WHERE telegram_id=$2", tg_hash, tg_id)
        updated += 1

    await conn.close()
    print(f"🎉 Migration complete! {updated} users updated.")

if __name__ == "__main__":
    asyncio.run(migrate())
