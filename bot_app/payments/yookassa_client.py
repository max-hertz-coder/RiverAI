from __future__ import annotations

import uuid
from typing import Dict, Any
import os

from yookassa import Configuration, Payment
from bot_app import config


def _configure() -> None:
    if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET_KEY:
        raise RuntimeError("YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY are not set")
    Configuration.account_id = str(config.YOOKASSA_SHOP_ID)
    Configuration.secret_key = str(config.YOOKASSA_SECRET_KEY)


def _build_receipt(amount_rub: int, description: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    # Если нужно отключить чек (например, в тестах): YOOKASSA_SEND_RECEIPT=0
    send_receipt = (os.getenv("YOOKASSA_SEND_RECEIPT", "1") != "0")

    if not send_receipt:
        return {}

    # VAT: по умолчанию 4 (без НДС). Переопределяется секретом YOOKASSA_VAT_CODE (1..6)
    vat_code = int(os.getenv("YOOKASSA_VAT_CODE", "4"))
    # Опционально система налогообложения (1..6) — если настроено в ЛК, можно не передавать
    tax_system_code = os.getenv("YOOKASSA_TAX_SYSTEM_CODE")
    try:
        tax_system_code = int(tax_system_code) if tax_system_code else None
    except Exception:
        tax_system_code = None

    # Контакты покупателя — возьмём из metadata, иначе синтетический email
    user_id = int((metadata or {}).get("user_id") or 0)
    email = (metadata or {}).get("email") or f"tg{user_id}@repboost.ru"
    phone = (metadata or {}).get("phone")  # если когда-то начнём его собирать

    customer: Dict[str, Any] = {}
    if email:
        customer["email"] = str(email)
    if phone:
        customer["phone"] = str(phone)

    receipt: Dict[str, Any] = {
        "customer": customer,
        "items": [{
            "description": (description or "Подписка RepBoost")[:127],
            "quantity": "1.00",
            "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
            "vat_code": vat_code,
            "payment_mode": "full_prepayment",
            "payment_subject": "service",
        }],
    }
    if tax_system_code:
        receipt["tax_system_code"] = tax_system_code

    return receipt


def create_invoice(amount_rub: int, description: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    _configure()
    idem = str(uuid.uuid4())

    payload: Dict[str, Any] = {
        "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": config.PAYMENT_RETURN_URL},
        "capture": True,
        "description": (description or "")[:127],
        "metadata": metadata or {},
    }

    receipt = _build_receipt(amount_rub, description, metadata)
    if receipt:
        payload["receipt"] = receipt

    payment = Payment.create(payload, idem)
    return {
        "payment_id": payment.id,
        "pay_url": payment.confirmation.confirmation_url,
        "status": str(payment.status),
    }


def fetch_status(payment_id: str) -> str:
    _configure()
    payment = Payment.find_one(payment_id)
    return str(payment.status)
