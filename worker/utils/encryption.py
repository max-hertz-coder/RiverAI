import base64
import hashlib
import os
from Crypto.Cipher import AES
from cryptography.fernet import Fernet
from worker import config

# AES ключ (используется для базового шифрования)
KEY = config.ENCRYPTION_KEY

# ================= AES (для внутренних служебных данных) ===================

def decrypt_str(encrypted_base64: str) -> str:
    try:
        data = base64.b64decode(encrypted_base64)
        nonce = data[:16]
        tag = data[16:32]
        ciphertext = data[32:]
        cipher = AES.new(KEY, AES.MODE_EAX, nonce=nonce)
        plaintext_bytes = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext_bytes.decode("utf-8")
    except Exception:
        return ""

# ================= Fernet (для промтов, входных данных, class_name и др.) ===================

def get_fernet():
    secret = os.getenv("WORKER_ENCRYPTION_SECRET")
    if not secret:
        raise RuntimeError("WORKER_ENCRYPTION_SECRET not found in environment")
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

def encrypt_worker_data(plaintext: str) -> str:
    return get_fernet().encrypt(plaintext.encode()).decode()

def decrypt_worker_data(ciphertext: str) -> str:
    return get_fernet().decrypt(ciphertext.encode()).decode()
