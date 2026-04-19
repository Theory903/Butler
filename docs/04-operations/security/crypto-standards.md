# Cryptography Standards

> **For:** Engineering, Security Team  
> **Status:** Production Required  
> **Version:** 1.0

---

## 1. Algorithms

### 1.1 Symmetric Encryption

| Use Case | Algorithm | Mode | Key Size |
|----------|-----------|------|-----------|
| Database fields | AES-256 | GCM | 256 bits |
| Object storage | AES-256 | GCM | 256 bits |
| Backups | AES-256 | GCM | 256 bits |
| Log archives | AES-256 | GCM | 256 bits |
| Field-level | AES-256 | GCM | 256 bits |

**Why GCM?** NIST SP 800-38D specifies GCM as the preferred authenticated encryption mode.

### 1.2 Asymmetric Encryption

| Use Case | Algorithm | Key Size |
|----------|-----------|-----------|
| Key wrapping | RSA-OAEP | 2048 bits |
| Digital signatures | ECDSA | P-256 |
| Key exchange | X25519 | 256 bits |

### 1.3 Hashing

| Use Case | Algorithm | Output |
|----------|-----------|--------|
| Passwords | Argon2id | 256 bits |
| Integrity | SHA-256 | 256 bits |
| HMAC | HMAC-SHA-256 | 256 bits |

---

## 2. Implementation

### 2.1 AES-GCM Encryption

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os

class AESCipher:
    def __init__(self, key: bytes):  # 256-bit key
        assert len(key) == 32
        self.aesgcm = AESGCM(key)
    
    def encrypt(self, plaintext: bytes, associated_data: bytes = None) -> bytes:
        nonce = os.urandom(12)  # 96-bit nonce
        ciphertext = self.aesgcm.encrypt(nonce, plaintext, associated_data)
        return nonce + ciphertext
    
    def decrypt(self, ciphertext: bytes, associated_data: bytes = None) -> bytes:
        nonce = ciphertext[:12]
        return self.aesgcm.decrypt(nonce, ciphertext[12:], associated_data)
```

### 2.2 Argon2id Password Hashing

```python
import argon2

class PasswordHasher:
    def __init__(self):
        self.hasher = argon2.PasswordHasher(
            time_cost=3,
            memory_cost=65536,  # 64 MB
            parallelism=4,
            hash_len=32,
            salt_len=16,
            type=argon2.Type.ID
        )
    
    def hash(self, password: str) -> str:
        return self.hasher.hash(password)
    
    def verify(self, hash: str, password: str) -> bool:
        try:
            return self.hasher.verify(hash, password)
        except:
            return False
```

### 2.3 IV/Nonce Requirements

**CRITICAL:** Never reuse nonce/IV with same key.

```python
# WRONG - reuse vulnerability
iv = os.urandom(12)
cipher1 = aes.encrypt(iv, plaintext1)
cipher2 = aes.encrypt(iv, plaintext2)  # BROKEN

# CORRECT - unique per encryption
iv1 = os.urandom(12)
iv2 = os.urandom(12)
cipher1 = aes.encrypt(iv1, plaintext1)
cipher2 = aes.encrypt(iv2, plaintext2)
```

---

## 3. Compliance

| Standard | Requirement |
|----------|-------------|
| NIST SP 800-38D | Use GCM mode |
| NIST SP 800-132 | Key derivation for passwords |
| OWASP | Use Argon2id for passwords |

---

*Document owner: Security Team*  
*Version: 1.0*