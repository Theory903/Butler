# Hermes → Butler Unified Runtime Merge Map

## Classification Legend

- **ABSORB_DIRECTLY**: Useful code copied/adapted into Butler runtime
- **WRAP_WITH_GOVERNANCE**: Useful but must pass ToolExecutor/security
- **REWRITE_BUTLER_NATIVE**: Concept useful, implementation too CLI/Hermes-specific
- **DROP_FROM_RUNTIME**: CLI/TUI/SQLite/local-home behavior not usable in server
- **KEEP_COMPAT_ONLY**: Legacy import shim

---

## Phase 1: Core Agent Runtime

### run_agent.py (~12k LOC)
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| AIAgent class | Core conversation loop with tool calling | butler_runtime/agent/loop.py | REWRITE_BUTLER_NATIVE | Pending |
| IterationBudget | Thread-safe iteration counter with refund | butler_runtime/agent/budget.py | ABSORB_DIRECTLY | Pending |
| _SafeWriter | Stdio wrapper for broken pipes | DROP_FROM_RUNTIME | CLI-only | - |
| Proxy handling | HTTP/HTTPS proxy configuration | infrastructure/config.py | ABSORB_DIRECTLY | Pending |
| Parallel tool execution | ThreadPoolExecutor for concurrent tools | butler_runtime/tools/executor.py | ABSORB_DIRECTLY | Pending |
| Destructive pattern detection | Shell command safety checks | butler_runtime/tools/risk.py | ABSORB_DIRECTLY | Pending |

### model_tools.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| get_tool_definitions | Tool schema discovery | butler_runtime/tools/registry.py | ABSORB_DIRECTLY | Pending |
| handle_function_call | Tool execution dispatcher | butler_runtime/tools/executor.py | REWRITE_BUTLER_NATIVE | Pending |
| _run_async | Sync→async bridging | butler_runtime/execution/ | ABSORB_DIRECTLY | Pending |
| TOOL_TO_TOOLSET_MAP | Tool categorization | butler_runtime/tools/registry.py | ABSORB_DIRECTLY | Pending |

### tools/registry.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| ToolRegistry | Central tool registry | butler_runtime/tools/registry.py | ABSORB_DIRECTLY | Pending |
| ToolEntry | Tool metadata | butler_runtime/tools/schemas.py | ABSORB_DIRECTLY | Pending |
| discover_builtin_tools | Auto-discovery of tool modules | butler_runtime/tools/registry.py | ABSORB_DIRECTLY | Pending |

### hermes_state.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| SessionDB | SQLite session store with FTS5 | DROP_FROM_RUNTIME | Butler uses Postgres | - |
| Session persistence | Session metadata and messages | services/orchestrator/session.py | REWRITE_BUTLER_NATIVE | Pending |

---

## Phase 2: Agent Internals

### agent/memory_manager.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| build_memory_context_block | Memory context assembly | services/memory/context_builder.py | ABSORB_DIRECTLY | Already enhanced |
| sanitize_context | PII/redaction handling | services/memory/consent_manager.py | ABSORB_DIRECTLY | Pending |

### agent/context_compressor.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| ContextCompressor | Context length management | services/memory/context_builder.py | ABSORB_DIRECTLY | Already enhanced |

### agent/prompt_builder.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| build_skills_system_prompt | Skills prompt assembly | butler_runtime/skills/compiler.py | REWRITE_BUTLER_NATIVE | Pending |
| build_context_files_prompt | File context prompt | butler_runtime/tools/context.py | ABSORB_DIRECTLY | Pending |
| MEMORY_GUIDANCE | Memory prompt templates | services/memory/context_builder.py | ABSORB_DIRECTLY | Already enhanced |

### agent/error_classifier.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| classify_api_error | API error classification | services/ml/error_handling.py | ABSORB_DIRECTLY | Pending |
| FailoverReason | Error type enumeration | services/ml/error_handling.py | ABSORB_DIRECTLY | Pending |

### agent/retry_utils.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| jittered_backoff | Exponential backoff with jitter | infrastructure/http/retry.py | ABSORB_DIRECTLY | Pending |

### agent/credential_pool.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| CredentialPool | Multi-provider credential management | services/ml/credential_pool.py | ABSORB_DIRECTLY | Pending |

### agent/usage_pricing.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| estimate_usage_cost | Token cost estimation | services/ml/pricing.py | ABSORB_DIRECTLY | Pending |

### agent/display.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| KawaiiSpinner | Animated CLI spinner | DROP_FROM_RUNTIME | CLI-only | - |
| build_tool_preview | Tool result formatting | DROP_FROM_RUNTIME | CLI-only | - |

---

## Phase 3: Provider Adapters

### agent/anthropic_adapter.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Anthropic provider | Claude API integration | services/ml/providers/anthropic.py | REWRITE_BUTLER_NATIVE | Pending |
| Cache control headers | Prompt caching optimization | services/ml/providers/anthropic.py | ABSORB_DIRECTLY | Pending |

### agent/bedrock_adapter.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| AWS Bedrock provider | Bedrock API integration | services/ml/providers/bedrock.py | REWRITE_BUTLER_NATIVE | Pending |

### agent/gemini_native_adapter.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Gemini provider | Google Gemini API | services/ml/providers/gemini.py | REWRITE_BUTLER_NATIVE | Pending |

### agent/gemini_cloudcode_adapter.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Cloud Code provider | VS Code integration | butler_runtime/providers/ | WRAP_WITH_GOVERNANCE | Pending |

### agent/auxiliary_client.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Auxiliary API client | Web search/extraction | butler_runtime/hermes/providers/auxiliary.py | REWRITE_BUTLER_NATIVE | Pending |

---

## Phase 4: Tool Implementations

### tools/file_operations.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| ShellFileOperations | File manipulation via shell | butler_runtime/hermes/tools/file.py | REWRITE_BUTLER_NATIVE | Already Butlerified |
| ReadResult, WriteResult | File operation result types | butler_runtime/tools/schemas.py | ABSORB_DIRECTLY | Pending |

### tools/file_tools.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| read_file_tool, write_file_tool | High-level file operations | butler_runtime/hermes/tools/file.py | REWRITE_BUTLER_NATIVE | Already Butlerified |

### tools/web_tools.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| web_search_tool, web_extract_tool | Web search and extraction | butler_runtime/hermes/tools/web.py | REWRITE_BUTLER_NATIVE | Already Butlerified |

### tools/code_execution_tool.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| execute_code | Code execution in environments | butler_runtime/hermes/tools/code.py | WRAP_WITH_GOVERNANCE | Deferred |

### tools/browser_tool.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Browser automation | Web browser control | butler_runtime/hermes/tools/browser.py | WRAP_WITH_GOVERNANCE | Pending |

### tools/terminal_tool.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Shell command execution | Terminal operations | butler_runtime/hermes/tools/shell.py | WRAP_WITH_GOVERNANCE | Pending |

### tools/memory_tool.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| memory_search, memory_store | Memory operations | butler_runtime/hermes/tools/memory.py | REWRITE_BUTLER_NATIVE | Must call Butler MemoryService |

### tools/fuzzy_match.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| fuzzy_find_and_replace | Text matching/replacement | butler_runtime/hermes/tools/utility.py | ABSORB_DIRECTLY | Direct import |

### tools/ansi_strip.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| strip_ansi | ANSI escape sequence removal | butler_runtime/hermes/tools/utility.py | ABSORB_DIRECTLY | Direct import |

### tools/path_security.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| validate_within_dir | Path validation | butler_runtime/tools/risk.py | ABSORB_DIRECTLY | Direct import |

### tools/url_safety.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| is_safe_url | SSRF protection | butler_runtime/hermes/tools/utility.py | REWRITE_BUTLER_NATIVE | Already Butlerified |

### tools/osv_check.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| check_package_for_malware | OSV malware check | butler_runtime/hermes/tools/utility.py | ABSORB_DIRECTLY | Direct import |

---

## Phase 5: Environment Backends

### tools/environments/local.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Local terminal backend | Local shell execution | butler_runtime/hermes/environments/local.py | WRAP_WITH_GOVERNANCE | Pending |

### tools/environments/docker.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Docker container backend | Containerized execution | butler_runtime/hermes/environments/docker.py | WRAP_WITH_GOVERNANCE | Pending |

### tools/environments/ssh.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| SSH remote execution | Remote shell access | butler_runtime/hermes/environments/ssh.py | WRAP_WITH_GOVERNANCE | Pending |

### tools/environments/modal.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Modal cloud backend | Modal cloud execution | butler_runtime/hermes/environments/modal.py | WRAP_WITH_GOVERNANCE | Pending |

---

## Phase 6: Gateway Platform Adapters

### gateway/platforms/telegram.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Telegram bot adapter | Telegram messaging | services/gateway/channels/telegram.py | REWRITE_BUTLER_NATIVE | Pending |

### gateway/platforms/discord.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Discord bot adapter | Discord messaging | services/gateway/channels/discord.py | REWRITE_BUTLER_NATIVE | Pending |

### gateway/platforms/slack.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Slack adapter | Slack messaging | services/gateway/channels/slack.py | REWRITE_BUTLER_NATIVE | Pending |

### gateway/platforms/whatsapp.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| WhatsApp adapter | WhatsApp messaging | services/gateway/channels/whatsapp.py | REWRITE_BUTLER_NATIVE | Pending |

### gateway/platforms/email.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Email adapter | Email messaging | services/gateway/channels/email.py | REWRITE_BUTLER_NATIVE | Pending |

### gateway/platforms/homeassistant.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Home Assistant adapter | Smart home integration | services/gateway/channels/homeassistant.py | REWRITE_BUTLER_NATIVE | Pending |

---

## Phase 7: Skills

### skills/ (all skill directories)
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Skill definitions | Domain-specific prompts | butler_runtime/skills/ | REWRITE_BUTLER_NATIVE | Pending |
| Skill loading | Skill discovery and parsing | butler_runtime/skills/loader.py | REWRITE_BUTLER_NATIVE | Pending |
| Skill compilation | Skill manifest generation | butler_runtime/skills/compiler.py | REWRITE_BUTLER_NATIVE | Pending |

---

## Phase 8: CLI/TUI (Drop from Runtime)

### cli.py
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| HermesCLI class | Interactive CLI orchestrator | DROP_FROM_RUNTIME | CLI-only | - |
| Rich/prompt_toolkit | Terminal UI | DROP_FROM_RUNTIME | CLI-only | - |
| Skin engine | CLI theming | DROP_FROM_RUNTIME | CLI-only | - |

### ui-tui/
| Component | What it does | Butler target | Merge strategy | Status |
|-----------|--------------|---------------|----------------|--------|
| Ink React UI | Terminal UI | DROP_FROM_RUNTIME | CLI-only | - |
| tui_gateway | JSON-RPC backend | DROP_FROM_RUNTIME | CLI-only | - |

---

## Summary Statistics

- **ABSORB_DIRECTLY**: 15 components
- **WRAP_WITH_GOVERNANCE**: 8 components
- **REWRITE_BUTLER_NATIVE**: 25 components
- **DROP_FROM_RUNTIME**: 8 components (CLI/TUI/SQLite)
- **KEEP_COMPAT_ONLY**: 0 components

**Total**: 56 components to process across 13 phases
