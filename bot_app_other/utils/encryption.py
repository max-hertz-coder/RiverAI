from Crypto.Cipher import AES
import base64
from bot_app import config

# Use AES in EAX mode for encryption/authentication
KEY = config.ENCRYPTION_KEY

def encrypt_str(plaintext: str) -> str:
    """
    Encrypt a plaintext string using AES encryption.
    Returns base64-encoded ciphertext including nonce and tag.
    """
    cipher = AES.new(KEY, AES.MODE_EAX)
    plaintext_bytes = plaintext.encode('utf-8')
    ciphertext, tag = cipher.encrypt_and_digest(plaintext_bytes)
    # Combine nonce, tag, and ciphertext for storage
    encrypted_bytes = cipher.nonce + tag + ciphertext
    # Return as base64 string for safe storage in text field
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