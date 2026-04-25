# Butler Tool Integration Inventory

Full inventory of all discovered tools across the Butler backend.

**Generated:** Phase T0 - Tool Integration
**Purpose:** Classify every tool by source, category, risk tier, and integration status before canonical integration.

---

## Inventory Table

| Tool Name | Source File | Source System | Category | Risk Tier | Status | Runtime Path | Needs Sandbox | Needs Approval | Needs Tenant Scope | Action |
|-----------|-------------|---------------|----------|-----------|--------|--------------|---------------|----------------|--------------------|--------|
| fuzzy_find_and_replace | butler_runtime/hermes/tools/utility.py | butler_runtime_legacy | utility | L0 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| strip_ansi | butler_runtime/hermes/tools/utility.py | butler_runtime_legacy | utility | L0 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| is_safe_url | butler_runtime/hermes/tools/utility.py | butler_runtime_legacy | utility | L0 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| check_package_for_malware | butler_runtime/hermes/tools/utility.py | butler_runtime_legacy | utility | L1 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| web_search | butler_runtime/hermes/tools/web.py | butler_runtime_legacy | web | L1 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| web_extract | butler_runtime/hermes/tools/web.py | butler_runtime_legacy | web | L1 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| read_file | butler_runtime/hermes/tools/file.py | butler_runtime_legacy | file | L2 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical, sandbox |
| write_file | butler_runtime/hermes/tools/file.py | butler_runtime_legacy | file | L2 | legacy-source | butler_runtime/hermes | No | Yes | Yes | Adapt to canonical, sandbox |
| list_files | butler_runtime/hermes/tools/file.py | butler_runtime_legacy | file | L2 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| search_files | butler_runtime/hermes/tools/file.py | butler_runtime_legacy | file | L2 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| memory_search | butler_runtime/hermes/tools/memory.py | butler_runtime_legacy | memory | L1 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| memory_store | butler_runtime/hermes/tools/memory.py | butler_runtime_legacy | memory | L2 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| memory_update_preference | butler_runtime/hermes/tools/memory.py | butler_runtime_legacy | memory | L2 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| memory_forget | butler_runtime/hermes/tools/memory.py | butler_runtime_legacy | memory | L2 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| memory_context | butler_runtime/hermes/tools/memory.py | butler_runtime_legacy | memory | L1 | legacy-source | butler_runtime/hermes | No | No | Yes | Adapt to canonical |
| terminal_tool | tools/terminal_tool.py | canonical_service_tool | terminal | L3 | unsafe | tools/ | Yes | Yes | Yes | Harden and sandbox |
| docker_environment | integrations/hermes/tools/environments/docker.py | hermes_legacy | environment | L3 | legacy-source | integrations/hermes | Yes | Yes | Yes | Adapt to canonical |
| ButlerLangChainTool | langchain/tools.py | langchain_tool | adapter | N/A | adapted | langchain | No | No | Yes | Ensure uses canonical executor |
| MCP tools (via mcp_bridge) | services/tools/mcp_bridge.py | mcp_tool | mcp | L1-L3 | adapted | services/tools | Varies | Varies | Yes | Ensure uses canonical executor |
| Skills (70+ from skills_library) | skills_library/*/SKILL.md | openclaw_skill | skills | L1-L3 | legacy-source | skills_library | Varies | Varies | Yes | Batch adapt to canonical |
| ButlerToolSpec (registry) | services/tools/registry.py | canonical_service_tool | registry | N/A | canonical | services/tools | No | No | Yes | Already canonical |
| ToolExecutor | services/tools/executor.py | canonical_service_tool | executor | N/A | canonical | services/tools | No | No | Yes | Already canonical |
| SkillsHub | services/tools/skills_hub.py | canonical_service_tool | skills | N/A | canonical | services/tools | No | No | Yes | Already canonical |
| SkillMarketplace | services/tools/skill_marketplace.py | canonical_service_tool | marketplace | N/A | canonical | services/tools | No | No | Yes | Already canonical |

---

## Source Systems

- **canonical_service_tool**: Tools defined in services/tools/ as Butler-native
- **langchain_tool**: Tools defined in langchain/ using LangChain patterns
- **mcp_tool**: Tools exposed via Model Context Protocol
- **a2a_tool**: Tools exposed via Agent-to-Agent protocol
- **acp_tool**: Tools exposed via Agent Control Protocol
- **butler_runtime_legacy**: Tools from butler_runtime/ package (migration target)
- **hermes_legacy**: Tools from integrations/hermes/ (Hermes legacy)
- **openclaw_skill**: Skills from skills_library/ (OpenClaw legacy)
- **service_internal_tool**: Internal service capabilities exposed as tools
- **cli_only**: CLI-only tools not exposed to API
- **test_tool**: Test-only tools not for production

---

## Status Definitions

- **canonical**: Already integrated into canonical Butler Tool Runtime
- **adapted**: Has adapter, needs integration
- **duplicate**: Duplicate of another tool, needs deduplication
- **legacy-source**: Legacy tool source, needs migration
- **unsafe**: Tool has security risks, needs hardening
- **blocked**: Tool is blocked/disabled
- **test-only**: Test tool, not for production
- **candidate-for-removal**: Tool may be removed after migration

---

## Risk Tiers

- **L0**: safe read-only, no approval
- **L1**: personal data read / low-risk generated output, logged
- **L2**: mutation / communication / scheduling / file write, approval
- **L3**: code execution / browser automation / device control / sandbox
- **L4**: financial / legal / destructive / credentialed action, critical approval

---

## Discovered Tool Locations

### services/tools/
- registry.py - Butler-native tool registry
- executor.py - Butler tool executor
- mcp_bridge.py - MCP tool bridge
- skills_hub.py - Skills hub
- skill_marketplace.py - Skill marketplace

### tools/
- registry.py - Tool registry
- terminal_tool.py - Terminal tool
- environments/ - Tool environments

### skills_library/ (70+ OpenClaw skills)
- 1password/
- apple-notes/
- apple-reminders/
- bear-notes/
- blogwatcher/
- blucli/
- bluebubbles/
- camsnap/
- canvas/
- clawhub/
- coding-agent/
- discord/
- eightctl/
- gemini/
- gh-issues/
- gifgrep/
- github/
- gog/
- goplaces/
- healthcheck/
- himalaya/
- imsg/
- mcporter/
- model-usage/
- nano-pdf/
- node-connect/
- notion/
- obsidian/
- openai-whisper/
- openai-whisper-api/
- openhue/
- oracle/
- ordercli/
- peekaboo/
- sag/
- session-logs/
- sherpa-onnx-tts/
- skill-creator/
- slack/
- songsee/
- sonoscli/
- spotify-player/
- summarize/
- taskflow/
- taskflow-inbox-triage/
- things-mac/
- tmux/
- trello/
- video-frames/
- voice-call/
- wacli/
- weather/
- xurl/

### butler_runtime/tools/
- (Legacy Butler runtime tools)

### butler_runtime/skills/
- (Legacy Butler runtime skills)

### butler_runtime/hermes/tools/
- utility.py
- memory.py
- web.py
- file.py

### integrations/hermes/tools/
- (Hermes legacy tools)

### langchain/
- tools.py - LangChain tools
- skills/ - LangChain skills
- protocols/mcp.py - MCP protocol
- protocols/acp.py - ACP protocol

### domain/tools/
- spec.py - Canonical ToolSpec contract
- hermes_compiler.py - Hermes tool compiler
- butler_tool_registry.py - Butler tool registry

---

## Summary

**Total Tools Discovered:** 24+ (excluding 70+ skills_library skills)
**Canonical Tools:** 4 (ButlerToolSpec, ToolExecutor, SkillsHub, SkillMarketplace)
**Legacy Butler Runtime Tools:** 16 (utility, web, file, memory tools)
**LangChain Tools:** 1 (ButlerLangChainTool adapter)
**MCP Tools:** 1 (via mcp_bridge, dynamic)
**Skills Library:** 70+ (OpenClaw skills)
**Service Internal Tools:** TBD (need to scan services/)

---

## Next Steps

1. Complete scanning of services/ directory for service-internal tools
2. Scan butler_runtime/skills/ for additional tools
3. Scan integrations/hermes/ for additional Hermes tools
4. Classify service-internal tools by risk tier and category
5. Populate remaining inventory entries
6. Proceed to Phase T1 - Update canonical ToolSpec contract

---

**Status:** Phase T0 in progress - initial inventory populated, scanning in progress
