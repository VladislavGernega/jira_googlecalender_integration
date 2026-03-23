# tests/test_encryption.py
import pytest
from sync.encryption import TokenEncryptor

class TestTokenEncryptor:
    def test_encrypt_decrypt_roundtrip(self, encryption_key):
        encryptor = TokenEncryptor(encryption_key)
        original = '{"access_token": "secret123", "refresh_token": "refresh456"}'

        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == original
        assert encrypted != original

    def test_encrypted_value_is_different_each_time(self, encryption_key):
        encryptor = TokenEncryptor(encryption_key)
        original = 'test-token'

        encrypted1 = encryptor.encrypt(original)
        encrypted2 = encryptor.encrypt(original)

        # Fernet includes timestamp, so same plaintext produces different ciphertext
        assert encrypted1 != encrypted2

    def test_decrypt_invalid_token_raises_error(self, encryption_key):
        encryptor = TokenEncryptor(encryption_key)

        with pytest.raises(Exception):
            encryptor.decrypt('invalid-not-base64-fernet-token')
