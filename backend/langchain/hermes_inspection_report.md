# Hermes Tool Inspection Report

## Phase 1: Tool Implementation Analysis

### Registry Analysis

**File:** `tools/registry.py`
- **Status:** CLEAN - Can be used directly
- **Dependencies:** None (no imports from other Hermes modules)
- **Key Functions:**
  - `registry.register()` - Tool registration
  - `registry.dispatch()` - Tool execution
  - `discover_builtin_tools()` - Auto-discovers tool modules
- **Butler Action:** DIRECT_IMPORT - Can use Butler-owned wrapper around this

### Model Tools Analysis

**File:** `model_tools.py`
- **Status:** PROBLEMATIC - Has Hermes-specific imports
- **Dependencies:** 
  - `from toolsets import ...` (needs fixing)
  - Calls `discover_builtin_tools()` which triggers all tool imports
- **Key Functions:**
  - `get_tool_definitions()` - Returns OpenAI tool schemas
  - `handle_function_call()` - Executes tools
- **Butler Action:** COPY_AND_BUTLERIFY - Need Butler-owned version

### Tool File Import Analysis

#### High-Dependency Tools (COPY_AND_BUTLERIFY)

**file_tools.py**
- **Tools:** `read_file_tool`, `write_file_tool`, `list_files_tool`
- **Dependencies:** 
  - `from tools.file_operations import ShellFileOperations`
  - `from tools.terminal_tool import _active_environments, _env_lock`
  - `from integrations.hermes.agent.file_safety import get_read_block_error`
  - `from integrations.hermes.tools.binary_extensions import has_binary_extension`
- **Butler Action:** COPY_AND_BUTLERIFY - Has complex internal dependencies

**code_execution_tool.py**
- **Tools:** `code_execution_tool`
- **Dependencies:**
  - `from tools.terminal_tool import ...`
  - `from tools.ansi_strip import strip_ansi`
  - `from tools.environments.base import touch_activity_if_due`
  - `from tools.interrupt import is_interrupted`
  - `from tools.env_passthrough import is_env_passthrough`
- **Butler Action:** COPY_AND_BUTLERIFY - Heavy dependencies on terminal/environments

**terminal_tool.py**
- **Tools:** Terminal execution, environment management
- **Dependencies:**
  - `from tools.environments.daytona import DaytonaEnvironment`
  - `from tools.process_registry import process_registry`
  - `from tools.file_tools import clear_file_ops_cache`
- **Butler Action:** COPY_AND_BUTLERIFY - Core infrastructure tool

#### Medium-Dependency Tools (WRAP_CLASS)

**web_tools.py**
- **Tools:** `web_search_tool`, `web_extract_tool`, `web_browse_tool`
- **Dependencies:** 
  - Mostly external APIs (Parallel, Firecrawl)
  - Some internal utility imports
- **Butler Action:** WRAP_CLASS - Can wrap with Butler adapter

**browser_tool.py**
- **Tools:** Browser automation
- **Dependencies:**
  - `from tools.browser_cdp_tool import ...`
  - `from tools.browser_supervisor import SUPERVISOR_REGISTRY`
- **Butler Action:** WRAP_CLASS - If dependencies resolved

#### Low-Dependency Tools (DIRECT_IMPORT)

**fuzzy_match.py**
- **Tools:** `fuzzy_find_and_replace`, `fuzzy_match_tool`
- **Dependencies:** Only standard library (re, difflib, typing)
- **Butler Action:** DIRECT_IMPORT - Clean, no Hermes dependencies

**osv_check.py**
- **Tools:** `osv_check_tool`
- **Dependencies:** External API calls only
- **Butler Action:** DIRECT_IMPORT - Likely clean

**url_safety_check.py**
- **Tools:** `url_safety_check_tool`
- **Dependencies:** External API calls only
- **Butler Action:** DIRECT_IMPORT - Likely clean

### Shared Utility Modules (COPY_AND_BUTLERIFY)

These are imported by multiple tools and need to be Butlerified:

**file_operations.py**
- Used by: file_tools, patch_parser, skills_tool
- **Action:** COPY_AND_BUTLERIFY - Core file operations

**ansi_strip.py**
- Used by: code_execution_tool, approval, terminal_tool
- **Action:** COPY_AND_BUTLERIFY - Simple utility, easy to copy

**path_security.py**
- Used by: skill_manager_tool, skills_tool
- **Action:** COPY_AND_BUTLERIFY - Security-critical, needs Butler ownership

**interrupt.py**
- Used by: code_execution_tool, send_message_tool, mcp_tool
- **Action:** COPY_AND_BUTLERIFY - Interrupt mechanism

### CLI/Gateway/Memory Components (SKIP)

These should NOT be imported in Butler context:

- **gateway/** - All gateway platform adapters
- **hermes_cli/** - CLI components
- **hermes_state.py** - SessionDB (Butler has its own memory)
- **cron/** - Scheduler (Butler has its own scheduling)
- **ui-tui/** - Terminal UI
- **plugins/memory/** - Memory providers (Butler has MemoryService)

### Environment Backends (WRAP_CLASS)

**tools/environments/**
- **Files:** local.py, docker.py, ssh.py, modal.py, daytona.py, singularity.py
- **Action:** WRAP_CLASS - Butler has SandboxManager, can wrap these

### Tool Categories Mapping

#### Priority 1 (Immediate Integration)
- `web_search_tool` - DIRECT_IMPORT or WRAP_CLASS
- `web_extract_tool` - DIRECT_IMPORT or WRAP_CLASS
- `read_file_tool` - COPY_AND_BUTLERIFY
- `write_file_tool` - COPY_AND_BUTLERIFY
- `list_files_tool` - COPY_AND_BUTLERIFY
- `fuzzy_match_tool` - DIRECT_IMPORT
- `osv_check_tool` - DIRECT_IMPORT
- `url_safety_check_tool` - DIRECT_IMPORT

#### Priority 2 (Medium Priority)
- `code_execution_tool` - COPY_AND_BUTLERIFY (complex)
- `shell_execution` - COPY_AND_BUTLERIFY (via terminal_tool)
- `browser_automation` - WRAP_CLASS (if dependencies resolved)
- `json/yaml/csv utilities` - Need inspection

#### Priority 3 (Low Priority / Skip)
- MCP tools - Skip (Butler has its own MCP integration)
- Calendar/email/contact helpers - Need inspection
- Image/document tools - Need inspection
- Gateway delivery helpers - SKIP (Butler has its own delivery)
- Cron/scheduler helpers - SKIP (Butler has its own scheduling)

### Import Path Issues Summary

**Problem Pattern:** `from tools.xxx import yyy`
**Butler Path:** `from integrations.hermes.tools.xxx import yyy`
**Impact:** All internal tool-to-tool imports break

**Solution Options:**
1. **Mass sed replacement** - Replace all `from tools.` with `from integrations.hermes.tools.`
2. **Selective Butlerification** - Copy only high-value tools with complex dependencies
3. **Hybrid approach** - Direct import for clean tools, Butlerify complex ones

### Recommended Butler Integration Strategy

**Phase 1 (Immediate):**
- Direct import clean tools (fuzzy_match, osv_check, url_safety_check)
- Create Butler-owned registry
- Build LangChain adapter

**Phase 2 (Short-term):**
- Butlerify shared utilities (ansi_strip, path_security)
- Copy high-value tools (file_tools, web_tools)
- Integrate environment backends

**Phase 3 (Long-term):**
- Butlerify complex tools (code_execution, browser_automation)
- Integrate remaining tool categories
- Full testing and validation

### Next Steps

1. Create Butler-owned registry structure
2. Build safe loader for clean tools
3. Butlerify shared utilities first
4. Copy high-value tool implementations
5. Build LangChain adapter layer
6. Integrate with Butler governance
