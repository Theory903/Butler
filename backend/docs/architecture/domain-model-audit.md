# Domain Model Audit - Tenant/Account Scoping

This document audits all domain models for proper tenant_id and account_id scoping to ensure multi-tenant isolation.

## Audit Summary

**Total Models Audited:** 30+ domain models across 7 domain packages

**Models with Full Scoping (tenant_id + account_id):** 13 models
**Models with Partial Scoping (account_id only):** 2 models
**Models Without Scoping (global/identity):** 15+ models

## Models WITH tenant_id and account_id

### domain/tenant/models.py
- **TenantCredential** - Encrypted provider credentials per tenant
- **UsageEvent** - Billing and usage tracking per tenant/account
- **AuditEvent** - Security audit events per tenant/account
- **ApprovalRequest** - Approval workflow per tenant/account

### domain/memory/models.py
- **MemoryEntry** - Canonical memory record
- **ConversationTurn** - Individual conversation turn
- **KnowledgeEntity** - Extracted knowledge entities
- **KnowledgeEdge** - Entity relationships
- **ExplicitPreference** - User preferences
- **ExplicitDislike** - User negative signals
- **UserConstraint** - User-defined constraints
- **Episode** - Goal-oriented interaction episodes
- **Routine** - Recurring behavior patterns
- **KnowledgeChunk** - Chunked text units

### domain/tools/models.py
- **ToolExecution** - Tool invocation audit records

## Models WITH account_id only (no tenant_id)

### domain/device/models.py
- **DeviceRegistry** - Hardware registry (owner_account_id)
  - **Rationale:** Devices are account-scoped, not tenant-scoped
  - **Issue:** May need tenant_id for multi-tenant scenarios

### domain/meetings/models.py
- **Meeting** - Scheduled meetings (account_id)
  - **Rationale:** Meetings are account-scoped
  - **Issue:** May need tenant_id for multi-tenant scenarios
- **Transcription** - Meeting transcript (child of Meeting)
- **MeetingSummary** - Meeting summary (child of Meeting)

## Models WITHOUT tenant/account scoping (global/identity)

### domain/auth/models.py (Identity Layer)
- **Principal** - Root identity (sub)
- **Account** - Butler Account (aid)
- **Identity** - Authentication identities
- **PasskeyCredential** - WebAuthn credentials
- **Session** - Auth sessions
- **TokenFamily** - Refresh token families
- **VoiceProfile** - Voice fingerprints
- **OAuthClient** - OAuth applications
- **OAuthCode** - Authorization codes
- **RecoveryCode** - Backup recovery codes
- **PasswordResetToken** - Reset tokens

**Rationale:** These are tenant-agnostic identity layer models. Tenants are mapped to accounts, not principals.

### domain/tools/models.py (Global Registry)
- **ToolDefinition** - Tool registry entry
  - **Rationale:** Tool definitions are global across all tenants
  - **Issue:** May need tenant-specific tool configurations in the future

### domain/security/models.py (Pydantic Models)
- **TrustLevel** - Enum
- **ContentSource** - Pydantic model
- **DefenseDecision** - Pydantic model
- **PolicyInput** - Pydantic model
- **PolicyDecision** - Pydantic model
- **ActorContext** - Pydantic model (has account_id)
- **ToolGateRequest** - Pydantic model
- **ToolGateDecision** - Pydantic model
- **RetrievalDecision** - Pydantic model

**Rationale:** These are Pydantic models for in-memory use, not database models.

## Recommendations

### High Priority
1. **Add tenant_id to DeviceRegistry** - Devices should be tenant-scoped for proper isolation
2. **Add tenant_id to Meeting** - Meetings should be tenant-scoped for proper isolation

### Medium Priority
1. **Consider tenant-specific tool configurations** - ToolDefinition may need tenant overrides
2. **Review account-only models** - Ensure account_id is sufficient for isolation needs

### Low Priority
1. **Document identity-to-tenant mapping** - Clarify how principals map to tenants via accounts
2. **Review Pydantic models** - Ensure ActorContext and other models have proper scoping

## Index Verification

All models with tenant_id and account_id have composite indexes:
- `ix_memory_entries_tenant_account_*`
- `ix_conversation_turns_tenant_account_*`
- `ix_tool_executions_tenant_created`
- `ix_usage_events_*`
- `ix_audit_events_*`
- `ix_approval_requests_*`

**Status:** Indexes are properly configured for multi-tenant queries.

## Migration Required

No database migration required at this time. Future migrations may be needed:
1. Add tenant_id to devices table
2. Add tenant_id to meetings table
3. Add indexes for new tenant_id columns
