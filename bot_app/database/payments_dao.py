# bot_app/database/payments_dao.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime

from bot_app.database.db import _get_pool  # используем общий пул
from bot_app.utils.identity import hash_telegram_id


async def create_payment(
    user_id: int,
    provider: str,
    invoice_id: str,
    amount_rub: int,
    label: str = "",
    currency: str = "RUB",
    status: str = "pending",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    pool = _get_pool()
    user_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO payments (user_hash, provider, invoice_id, label, amount_rub, currency, status, meta)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (invoice_id) DO NOTHING
            """,
            user_hash, provider, invoice_id, label, int(amount_rub), currency, status, meta or {},
        )


async def get_payment(invoice_id: str) -> Optional[Dict[str, Any]]:
    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM payments WHERE invoice_id=$1", invoice_id)
    return dict(row) if row else None


async def update_status(invoice_id: str, status: str, paid_at: datetime | None = None) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE payments SET status=$1, paid_at=$2 WHERE invoice_id=$3",
            status, paid_at, invoice_id
        )


async def mark_paid(invoice_id: str) -> None:
    await update_status(invoice_id, "succeeded", datetime.utcnow())


async def get_user_payments(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    pool = _get_pool()
    user_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, provider, invoice_id, label, amount_rub, currency, status, created_at, paid_at
            FROM payments
            WHERE user_hash=$1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_hash, int(limit),
        )
    return [dict(r) for r in rows]
