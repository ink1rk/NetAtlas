"""AES-256-GCM secret vault."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from netatlas.domain.errors import SecretVaultError


class AesGcmSecretVault:
    """Encrypts credential material at rest using AES-256-GCM."""

    def __init__(self, master_key_b64: str) -> None:
        if not master_key_b64:
            raise SecretVaultError("NETATLAS_MASTER_KEY_B64 is required")
        try:
            key = base64.b64decode(master_key_b64, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise SecretVaultError("Master key must be valid base64") from exc
        if len(key) != 32:
            raise SecretVaultError("Master key must decode to exactly 32 bytes")
        self._gcm = AESGCM(key)

    def encrypt(self, plaintext: bytes, *, key_version: str = "v1") -> tuple[bytes, bytes, str]:
        nonce = os.urandom(12)
        ciphertext = self._gcm.encrypt(nonce, plaintext, key_version.encode("utf-8"))
        return ciphertext, nonce, key_version

    def decrypt(self, ciphertext: bytes, nonce: bytes, *, key_version: str = "v1") -> bytes:
        try:
            return self._gcm.decrypt(nonce, ciphertext, key_version.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise SecretVaultError("Failed to decrypt secret") from exc
