import os
import base64
import hashlib
from Crypto.Cipher import AES
from cryptography.fernet import Fernet

from bot_app import config

# AES ключ (для стандартных данных)
KEY: bytes = config.ENCRYPTION_KEY  # 16/24/32 bytes


def encrypt_str(plaintext: str) -> str:
    """
    Безопасное симметричное шифрование строки (AES-EAX).
    Возвращает base64(nonce|tag|ciphertext).
    """
    if plaintext is None:
        plaintext = ""
    cipher = AES.new(KEY, AES.MODE_EAX)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
    blob = cipher.nonce + tag + ciphertext
    return base64.b64encode(blob).decode("utf-8")


def decrypt_str(cipher_text: str) -> str:
    """
    Расшифровка строки, зашифрованной encrypt_str.
    Возвращает "" при любой ошибке.
    """
    if not cipher_text:
        return ""
    try:
        raw = base64.b64decode(cipher_text)
        nonce, tag, ciphertext = raw[:16], raw[16:32], raw[32:]
        cipher = AES.new(KEY, AES.MODE_EAX, nonce=nonce)
        data = cipher.decrypt_and_verify(ciphertext, tag)
        return data.decode("utf-8")
    except Exception:
        return ""


# -------- Fernet для токенов Яндекс.Диск --------

def _ydisk_fernet() -> Fernet:
    """
    Строим стабильный ключ Fernet из переменных окружения YDKEY_V{N}.
    """
    version = os.getenv("YDKEY_VERSION", "1")
    raw_key = os.getenv(f"YDKEY_V{version}")
    if not raw_key:
        raise RuntimeError(f"YDKEY_V{version} not found in environment")
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_ydisk_token(token: str) -> str:
    return _ydisk_fernet().encrypt((token or "").encode("utf-8")).decode("utf-8")


def decrypt_ydisk_token(token_enc: str) -> str:
    try:
        return _ydisk_fernet().decrypt((token_enc or "").encode("utf-8")).decode("utf-8")
    except Exception:
        return ""
