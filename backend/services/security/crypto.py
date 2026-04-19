from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

class AESCipher:
    """AES-256-GCM with versioning and AAD per security.md spec."""
    
    VERSION = b"\x01"
    
    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("AES-256 key must be 32 bytes")
        self._aesgcm = AESGCM(key)
    
    def encrypt(self, plaintext: bytes, aad: bytes = b"") -> bytes:
        nonce = os.urandom(12)  # 96-bit nonce
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, self.VERSION + aad)
        return self.VERSION + nonce + ciphertext
    
    def decrypt(self, blob: bytes, aad: bytes = b"") -> bytes:
        version = blob[:1]
        if version != self.VERSION:
            raise ValueError("Unsupported ciphertext version")
        nonce = blob[1:13]
        ciphertext = blob[13:]
        return self._aesgcm.decrypt(nonce, ciphertext, version + aad)

class KeyHierarchy:
    """Three-level key hierarchy: Root (KMS) → Domain KEKs → Data DEKs."""
    
    DOMAIN_KEKS = {
        "credentials": "kek_cred_v1",
        "user_secrets": "kek_user_v1",
        "memory_pii": "kek_pii_v1",
        "audit": "kek_audit_v1",
    }
    
    def get_domain_kek(self, domain: str) -> str:
        kek = self.DOMAIN_KEKS.get(domain)
        if not kek:
            raise ValueError(f"Unknown key domain: {domain}")
        return kek
