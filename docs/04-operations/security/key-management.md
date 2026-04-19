# Key Management

> **For:** Engineering, Security Team  
> **Status:** Production Required  
> **Version:** 1.0

---

## 1. Key Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                    KEY HIERARCHY                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Master Key (HSM/KMS)                                      │
│       │                                                      │
│       ├── Data Encryption Keys (DEK) per tenant/table       │
│       │       │                                              │
│       │       ├── PostgreSQL data key                       │
│       │       ├── Redis cache key                          │
│       │       ├── Backup encryption key                    │
│       │       └── Log archive key                          │
│       │                                                      │
│       └── Signing Keys                                      │
│               │                                              │
│               ├── JWT signing key                           │
│               ├── Webhook signing key                      │
│               └── API key encryption key                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Envelope Encryption

```python
class KeyManager:
    def __init__(self, kms_client):
        self.kms = kms_client
    
    async def generate_dek(self, owner: str, resource: str) -> DataEncryptionKey:
        """Generate data encryption key"""
        
        # Generate 256-bit key
        dek = os.urandom(32)
        
        # Wrap with master key
        wrapped = self.kms.encrypt(dek, f"{owner}:{resource}")
        
        return DataEncryptionKey(
            key_id=f"dek-{owner}-{resource}-{uuid4()}",
            encrypted_key=wrapped,
            algorithm="AES-256-GCM",
            created_at=datetime.utcnow()
        )
    
    async def decrypt_dek(self, encrypted_dek: bytes) -> bytes:
        """Decrypt data encryption key"""
        return self.kms.decrypt(encrypted_dek)
```

---

## 3. Key Rotation

### 3.1 Rotation Schedule

| Key Type | Rotation Period | Method |
|----------|----------------|--------|
| Master key | 1 year | HSM re-encryption |
| Data encryption keys | 90 days | Re-wrap |
| JWT signing keys | 30 days | Dual-running |
| API keys | 90 days | Re-issue |
| Webhook secrets | 180 days | Re-issue |

### 3.2 JWT Key Rotation

```python
class JWTSigner:
    def __init__(self, key_manager):
        self.key_manager = key_manager
        self.current_key_id = None
        self.previous_key_id = None
    
    async def sign(self, payload: dict) -> str:
        """Sign with current key, include previous for rotation"""
        
        now = datetime.utcnow()
        
        # Check if key needs rotation
        if self.should_rotate():
            await self.rotate_keys()
        
        # Sign with current key
        headers = {
            "alg": "RS256",
            "kid": self.current_key_id,
            "prev_kid": self.previous_key_id  # For verification during rotation
        }
        
        token = jwt.encode(payload, self.current_private_key, algorithm="RS256", headers=headers)
        
        return token
    
    def verify(self, token: str) -> dict:
        """Verify with either current or previous key"""
        
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        
        # Try current key
        try:
            return jwt.decode(token, self.current_public_key, algorithms=["RS256"])
        except:
            pass
        
        # Try previous key (for rotation window)
        if kid == self.previous_key_id:
            return jwt.decode(token, self.previous_public_key, algorithms=["RS256"])
        
        raise InvalidTokenError("Token signed with unknown key")
```

---

## 4. Secret Management

### 4.1 Storage

All secrets stored in:
- **HSM**: Master keys, signing keys
- **KMS**: Data encryption keys
- **Vault**: Application secrets (API keys, credentials)

### 4.2 Injection

```python
class SecretInjector:
    """Inject secrets at runtime from Vault"""
    
    def __init__(self, vault_client):
        self.vault = vault_client
    
    async def get_secret(self, path: str) -> dict:
        """Get secret from Vault"""
        
        secret = self.vault.read(path)
        
        # Inject into environment (for legacy apps)
        for key, value in secret.items():
            os.environ[key] = value
        
        return secret
    
    async def get_database_credentials(self) -> DatabaseCredentials:
        """Get rotated DB credentials"""
        
        creds = self.vault.read("database/credentials")
        
        return DatabaseCredentials(
            host=creds["host"],
            username=creds["username"],
            password=creds["password"],
            rotation_period=creds["rotation_period"]
        )
```

---

## 5. Key Lifecycle

| Phase | Actions |
|-------|--------|
| **Generation** | HSM-generated, never exported |
| **Distribution** | Encrypted transport, verify fingerprint |
| **Storage** | HSM/KMS only, no plaintext |
| **Use** | In-memory only, zero on release |
| **Rotation** | Dual-running, gradual rollout |
| **Revocation** | Immediate blocklist, audit |
| **Destruction** | HSM wipe, verification |

---

## 6. Emergency Procedures

### 6.1 Key Compromise

1. **Immediate** (0-15 min):
   - Revoke compromised keys
   - Enable enhanced monitoring
   - Notify security team

2. **Short-term** (15 min - 1 hour):
   - Rotate all dependent keys
   - Force re-encryption of data
   - Review access logs

3. **Recovery** (1-24 hours):
   - Restore from last known good state
   - Re-issue all credentials
   - Post-incident review

---

*Document owner: Security Team*  
*Version: 1.0*