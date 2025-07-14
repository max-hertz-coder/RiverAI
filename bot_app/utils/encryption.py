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

def decrypt_str(encrypted_base64: str) -> str:
    """
    Decrypt a base64-encoded ciphertext string using AES.
    Returns the original plaintext.
    """
    try:
        encrypted_bytes = base64.b64decode(encrypted_base64)
    except Exception:
        return ""  # if decoding fails, return empty (or raise)
    # The first 16 bytes are nonce, next 16 are tag, rest is ciphertext
    nonce = encrypted_bytes[:16]
    tag = encrypted_bytes[16:32]
    ciphertext = encrypted_bytes[32:]
    # Create cipher and decrypt
    cipher = AES.new(KEY, AES.MODE_EAX, nonce=nonce)
    try:
        plaintext_bytes = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext_bytes.decode('utf-8')
    except Exception:
        return ""  # if decryption fails (e.g. data tampered), return empty or handle error
