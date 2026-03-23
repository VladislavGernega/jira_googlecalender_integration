from cryptography.fernet import Fernet, InvalidToken

class TokenEncryptor:
    """Encrypts and decrypts OAuth tokens using Fernet (AES-128-CBC + HMAC-SHA256)."""

    def __init__(self, key: str):
        self.fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string and return base64-encoded ciphertext."""
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64-encoded ciphertext and return plaintext."""
        try:
            return self.fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as e:
            raise ValueError("Invalid or corrupted token") from e
