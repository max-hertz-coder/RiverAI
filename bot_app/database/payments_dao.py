# bot_app/database/payments_dao.py
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid

from bot_app.database.db import _get_pool
from bot_app.utils.identity import hash_telegram_id


def _gen_manual_invoice_id() -> str:
    return f"manual:{uuid.uuid4()}"


async def create_payment(
    user_id: int,
    provider: str,
    invoice_id: Optional[str],
    amount_rub: int,
    label: str = "",
    currency: str = "RUB",
    status: str = "pending",
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Создаёт запись о платеже. Возвращает invoice_id (сгенерирует, если None и provider='manual').
    """
    inv = invoice_id or (_gen_manual_invoice_id() if provider == "manual" else None)
    if not inv:
        raise ValueError("invoice_id is required for non-manual provider")

    pool = _get_pool()
    user_hash = hash_telegram_id(user_id)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO payments (user_hash, provider, invoice_id, label, amount_rub, currency, status, meta)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (invoice_id) DO NOTHING
            """,
            user_hash, provider, inv, label, int(amount_rub), currency, status, meta or {},
        )
    return inv


async def get_payment(invoice_id: str) -> Optional[Dict[str, Any]]:
    pool = _get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM payments WHERE invoice_id=$1", invoice_id)
    return dict(row) if row else None


async def update_status(invoice_id: str, status: str, paid_at: Optional[datetime] = None) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE payments SET status=$1, paid_at=$2 WHERE invoice_id=$3",
            status, paid_at, invoice_id,
        )


async def mark_paid(invoice_id: str) -> None:
    pool = _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE payments SET status='succeeded', paid_at=$1 WHERE invoice_id=$2",
            datetime.utcnow(), invoice_id,
        )


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
