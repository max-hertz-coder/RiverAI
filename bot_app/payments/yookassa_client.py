from __future__ import annotations

import uuid
from typing import Dict, Any

from yookassa import Configuration, Payment
from bot_app import config


def _configure() -> None:
    if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET_KEY:
        raise RuntimeError("YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY are not set")
    Configuration.account_id = str(config.YOOKASSA_SHOP_ID)
    Configuration.secret_key = str(config.YOOKASSA_SECRET_KEY)


def create_invoice(amount_rub: int, description: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    _configure()
    idem = str(uuid.uuid4())
    payment = Payment.create({
        "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": config.PAYMENT_RETURN_URL},
        "capture": True,
        "description": description[:127],
        "metadata": metadata or {},
    }, idem)
    return {"payment_id": payment.id, "pay_url": payment.confirmation.confirmation_url, "status": payment.status}


def fetch_status(payment_id: str) -> str:
    _configure()
    payment = Payment.find_one(payment_id)
    return str(payment.status)
