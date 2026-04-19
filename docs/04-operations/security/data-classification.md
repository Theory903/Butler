# Data Classification

> **For:** Engineering, Security, Product  
> **Status:** Production Required  
> **Version:** 1.0

---

## 1. Classification Levels

| Level | Definition | Examples | Handling |
|-------|------------|-----------|----------|
| **PUBLIC** | No restrictions | Marketing content, public docs | No encryption required, standard logging |
| **INTERNAL** | Company-only | Product roadmap, internal docs | Encrypt at rest, redact in logs |
| **SENSITIVE** | User/business data | Messages, contacts, preferences | Encrypt at rest + transit, full audit |
| **SECRET** | Highly restricted | Passwords, tokens, payment info | Field-level encryption, immutable audit |

---

## 2. Classification Matrix

| Data Type | Classification | Encryption | Retention | Logging |
|-----------|----------------|-------------|------------|---------|
| User email | SENSITIVE | AES-256 | Account + 30 days | Full |
| Message content | SENSITIVE | AES-256 | User choice | Full |
| Session token | SECRET | Field-level | Session + 7 days | Full |
| Refresh token | SECRET | Field-level | 30 days | Full |
| Password hash | SECRET | Argon2id | Permanent | Audit only |
| API keys | SECRET | Field-level | Per key | Full |
| Payment info | SECRET | Field-level | Per regulation | Full |
| Device tokens | SENSITIVE | AES-256 | Device lifetime | Full |
| Preferences | INTERNAL | AES-256 | User choice | None |
| Analytics | INTERNAL | None | 2 years | Aggregated |

---

## 3. Implementation

### 3.1 Classification Decorator

```python
from dataclasses import dataclass
from enum import Enum

class DataClass(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    SECRET = "secret"

@dataclass
class DataClassification:
    level: DataClass
    pii: bool = False
    pci: bool = False  # Payment card industry
    gdpr: bool = False
    retention_days: int = None
    encryption_required: bool = True

# Classification registry
DATA_CLASSIFICATIONS = {
    "user.email": DataClass.SENSITIVE, pii=True, gdpr=True, retention_days=30,
    "user.password_hash": DataClass.SECRET, pii=False, retention_days=None,
    "session.access_token": DataClass.SECRET, retention_days=None,
    "session.refresh_token": DataClass.SECRET, retention_days=30,
    "message.content": DataClass.SENSITIVE, pii=True, gdpr=True,
    "message.metadata": DataClass.INTERNAL,
    "preference.settings": DataClass.INTERNAL,
    "payment.info": DataClass.SECRET, pii=True, pci=True,
    "device.token": DataClass.SENSITIVE, retention_days=None,
}
```

### 3.2 Handling by Classification

```python
class DataHandler:
    def __init__(self, encryption_service, audit_logger):
        self.encryption = encryption_service
        self.audit = audit_logger
    
    async def store(self, key: str, value: any):
        """Store with appropriate handling based on classification"""
        
        classification = self.get_classification(key)
        
        # Encrypt if required
        if classification.encryption_required:
            value = await self.encryption.encrypt(value, classification.level)
        
        # Log based on classification
        if classification.level in [DataClass.SENSITIVE, DataClass.SECRET]:
            await self.audit.log_data_access(key, "write", classification.level)
        
        # Store
        await self.storage.set(key, value, ttl=classification.retention_days)
    
    async def retrieve(self, key: str) -> any:
        """Retrieve with appropriate handling"""
        
        classification = self.get_classification(key)
        value = await self.storage.get(key)
        
        # Log based on classification
        if classification.level in [DataClass.SENSITIVE, DataClass.SECRET]:
            await self.audit.log_data_access(key, "read", classification.level)
        
        # Decrypt if required
        if classification.encryption_required and value:
            value = await self.encryption.decrypt(value, classification.level)
        
        return value
```

---

## 4. Retention

| Classification | Retention | Deletion |
|----------------|-----------|----------|
| PUBLIC | No limit | Immediate |
| INTERNAL | 2 years | Standard wipe |
| SENSITIVE | Per user choice + 30 days | Crypto erase |
| SECRET | Per regulation | Crypto erase + verification |

---

## 5. Compliance

| Regulation | Requirements | Implementation |
|------------|--------------|----------------|
| GDPR | Consent, deletion, portability | User data exports, deletion API |
| CCPA | Opt-out, deletion | Do not sell flag, deletion |
| PCI-DSS | Tokenization, encryption | No raw PAN storage |
| SOC2 | Access logging, encryption | Full audit trail |

---

*Document owner: Security Team*  
*Version: 1.0*