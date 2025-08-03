from Crypto.Cipher import AES
import base64
from worker import config

KEY = config.ENCRYPTION_KEY

def decrypt_str(encrypted_base64: str) -> str:
    try:
        data = base64.b64decode(encrypted_base64)
    except Exception:
        return ""
    nonce = data[:16]
    tag = data[16:32]
    ciphertext = data[32:]
    cipher = AES.new(KEY, AES.MODE_EAX, nonce=nonce)
    try:
        plaintext_bytes = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext_bytes.decode('utf-8')
    except Exception:
        return ""
