import os
import base64
import hashlib
from Crypto.Cipher import AES
from cryptography.fernet import Fernet
from bot_app import config

# AES ключ (для стандартных данных)
KEY = config.ENCRYPTION_KEY

# ------------------ AES для обычного шифрования ------------------

def encrypt_str(plaintext: str) -> str:
    cipher = AES.new(KEY, AES.MODE_EAX)
    plaintext_bytes = plaintext.encode('utf-8')
    ciphertext, tag = cipher.encrypt_and_digest(plaintext_bytes)
    encrypted_bytes = cipher.nonce + tag + ciphertext
    return base64.b64encode(encrypted_bytes).decode('utf-8')

def decrypt_str(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    try:
        raw = base64.b64decode(cipher_text)
        nonce = raw[:16]
        tag = raw[16:32]
        ciphertext = raw[32:]
        cipher = AES.new(KEY, AES.MODE_EAX, nonce=nonce)
        decrypted = cipher.decrypt_and_verify(ciphertext, tag)
        return decrypted.decode("utf-8")
    except Exception:
        return ""

# ------------------ Fernet для Yandex Disk токенов ------------------

def get_ydisk_fernet():
    version = os.getenv("YDKEY_VERSION", "1")
    key_env = f"YDKEY_V{version}"
    raw_key = os.getenv(key_env)
    if not raw_key:
        raise RuntimeError(f"YDKEY_V{version} not found in environment")
    digest = hashlib.sha256(raw_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))

def encrypt_ydisk_token(token: str) -> str:
    return get_ydisk_fernet().encrypt(token.encode()).decode()

def decrypt_ydisk_token(token_enc: str) -> str:
    return get_ydisk_fernet().decrypt(token_enc.encode()).decode()
