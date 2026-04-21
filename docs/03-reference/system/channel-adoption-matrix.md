# Channel Adoption Matrix
> **Document Version:** 2.0 (Oracle-Grade)
> **Updated:** 2026-04-19
> **Workstream:** Reference Harvest Plan - Workstream 4
> **Owner:** Communication Service

---

## Channel Adoption Matrix

| Channel | Butler Owner Service | Hermes Role | Auth Mode | Approval Model | Portability Rating | Adopt Priority |
|---------|----------------------|-------------|-----------|----------------|--------------------|----------------|
| **WhatsApp** | Communication | Primary Adapter | OAuth 2.0 + Phone Binding | Explicit | 2 | P0 |
| **Telegram** | Communication | Primary Adapter | Bot Token | Implicit | 5 | P0 |
| **Slack** | Communication | Primary Adapter | OAuth 2.0 | Explicit | 4 | P0 |
| **Discord** | Communication | Primary Adapter | Bot Token | Implicit | 4 | P0 |
| **Signal** | Communication | Primary Adapter | Phone Binding | Explicit | 3 | P1 |
| **Matrix** | Communication | Primary Adapter | OAuth 2.0 | Implicit | 5 | P1 |
| **Teams** | Communication | Primary Adapter | OAuth 2.0 | Explicit | 3 | P1 |
| **Google Chat** | Communication | Primary Adapter | OAuth 2.0 | Explicit | 3 | P1 |
| **iMessage / BlueBubbles** | Communication | Secondary Adapter | Apple ID | Explicit | 1 | P2 |
| **Feishu** | Communication | Primary Adapter | OAuth 2.0 | Explicit | 3 | P2 |
| **LINE** | Communication | Primary Adapter | Bot Token | Implicit | 3 | P2 |
| **Mattermost** | Communication | Primary Adapter | Bot Token | Implicit | 5 | P2 |
| **Nostr** | Communication | Primary Adapter | Public Key | None | 5 | P2 |
| **Twitch** | Communication | Primary Adapter | OAuth 2.0 | Implicit | 3 | P2 |
| **QQ** | Communication | Secondary Adapter | Bot Token | Explicit | 2 | P3 |
| **WeChat** | Communication | Secondary Adapter | Official Account | Explicit | 1 | P3 |
| **Zalo** | Communication | Secondary Adapter | Bot Token | Explicit | 2 | P3 |
| **IRC** | Communication | Primary Adapter | NickServ | None | 5 | P3 |
| **Tlon / Urbit** | Communication | Secondary Adapter | Urbit ID | Implicit | 4 | P3 |
| **Synology Chat** | Communication | Secondary Adapter | API Token | Implicit | 4 | P3 |
| **Nextcloud Talk** | Communication | Secondary Adapter | OAuth 2.0 | Implicit | 4 | P3 |
| **WebChat** | Gateway | Native Adapter | Session Cookie | Implicit | 5 | P0 |
| **Voice Call** | Communication | Primary Adapter | Phone Number | Critical | 2 | P1 |
| **Email** | Communication | Primary Adapter | SMTP / OAuth | Explicit | 5 | P1 |
| **SMS** | Communication | Primary Adapter | Phone Number | Critical | 2 | P1 |
| **Webhook** | Gateway | Native Adapter | HMAC Signature | Explicit | 5 | P0 |
| **MCP Client** | Tools | Native Adapter | Instance Key | Implicit | 5 | P0 |
| **IoT** | Device | Native Adapter | Device Certificate | Explicit | 3 | P2 |

---

### Rating Definitions

| Rating | Definition |
|--------|------------|
| **Portability 1** | Platform locked, proprietary, no migration path |
| **Portability 2** | Mostly locked, limited export capabilities |
| **Portability 3** | Partial portability, message history export only |
| **Portability 4** | Good portability, standard protocols available |
| **Portability 5** | Fully open, standards-based, fully portable |

---

| Priority | Definition | Timeline |
|----------|------------|----------|
| **P0** | MVP Required | < 30 days |
| **P1** | Post-MVP Critical | 30-90 days |
| **P2** | High Value | 90-180 days |
| **P3** | Long Tail | > 180 days |

---

### Approval Model Definitions

| Model | Description |
|-------|-------------|
| **None** | No approval required, all messages auto-executed |
| **Implicit** | Approved by default, user can revoke after delivery |
| **Explicit** | User must approve action before execution |
| **Critical** | Multi-factor approval required for all actions |

---

## Channel Features Matrix

| Channel | Webhook Verification | Default Rate Limit | Message Format | Media Support | Delivery Semantics |
|---------|----------------------|--------------------|----------------|---------------|---------------------|
| WhatsApp | HMAC SHA256 | 1000 / minute | Markdown | Full | At-least-once |
| Telegram | Secret Token | 30 / second | Markdown V2 | Full | At-least-once |
| Slack | HMAC SHA256 | 1 / second | Mrkdwn | Full | At-least-once |
| Discord | Ed25519 Signature | 50 / second | Markdown | Full | At-least-once |
| Signal | None | 60 / minute | Plaintext | Full | Exactly-once |
| Matrix | HMAC SHA256 | Unlimited | Markdown | Full | Exactly-once |
| Teams | HMAC SHA256 | 30 / minute | Adaptive Cards | Full | At-least-once |
| WebChat | Session Signature | Unlimited | Markdown | Full | Exactly-once |
| Webhook | HMAC SHA256 | Unlimited | JSON | Binary | At-least-once |
| MCP Client | Instance Signature | Unlimited | Structured | Binary | Exactly-once |
| Email | DKIM / SPF | 10 / minute | HTML / Plaintext | Attachments | At-least-once |
| SMS | None | 1 / second | Plaintext | None | At-least-once |
| Voice Call | None | 1 / minute | Audio | None | At-most-once |

---

## Integration Rules

### 1. Hermes Connection Pattern

All external channels **MUST** go through Hermes adapter layer:

```
Channel → Hermes Adapter → Gateway → Orchestrator
```

- No direct channel connections to Butler services
- All authentication handled at Hermes boundary
- Hermes performs rate limiting and message normalization
- Hermes maintains channel delivery state

### 2. Gateway Connection Pattern

Native channels connect directly to Gateway:

```
Native Client → Gateway → Orchestrator
```

- Applies to: WebChat, Webhook, MCP Client, IoT
- Uses native Butler authentication
- Full end-to-end encryption
- Exactly-once delivery guarantees

### 3. Security Per Channel

| Channel Class | Transport Security | Message Encryption | Audit Logging |
|---------------|--------------------|--------------------|---------------|
| P0 Channels | TLS 1.3 Required | End-to-end | Full payload |
| P1 Channels | TLS 1.3 Required | End-to-end | Metadata only |
| P2 Channels | TLS 1.2+ Required | Transport only | Metadata only |
| P3 Channels | TLS 1.2+ Required | Transport only | Minimal |

### 4. Fallback Handling

- **Primary failure**: Channel goes down → queue messages for 72 hours
- **Secondary failure**: Primary channel down → notify user via highest priority alternate channel
- **Critical failure**: All channels down → persist to durable storage, notify on next connection
- **Rate limit hit**: Exponential backoff with jitter, maximum 15 minute retry interval

---

## Channel Onboarding Checklist

For each new channel:

1. ✅ Implement Hermes adapter
2. ✅ Define rate limits and backoff strategy
3. ✅ Map message formats to Butler canonical format
4. ✅ Implement authentication flow
5. ✅ Define approval model
6. ✅ Add delivery guarantees
7. ✅ Implement fallback handling
8. ✅ Add telemetry and metrics
9. ✅ Security review completed
10. ✅ Documentation added

---

## References

- [Communication Service Spec](../services/communication.md)
- [Hermes Adapter Specification](../infrastructure/hermes.md)
- [Security Policy](../security/SECURITY.md)
- [Delivery Guarantees](../system/delivery-semantics.md)

---

*This document is authoritative. All channel implementations must follow this matrix.*
