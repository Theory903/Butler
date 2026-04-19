# Plugin → Tool Pipeline

> **Purpose:** How plugins become callable tools  
> **Goal:** Extensible system, not hardcoded tools

---

## Overview

```
Plugin Uploaded → Tool Registered → Agent Can Call
```

One plugin = One or more tools. Simple.

---

## Pipeline Stages

```
Stage 1: Plugin Upload (REST API)
    ↓
Stage 2: Plugin Validation (schema check)
    ↓
Stage 3: Tool Registration (add to registry)
    ↓
Stage 4: Hot Reload (orchestrator refreshes)
    ↓
Stage 5: Ready to Call (available to agent)
```

---

## Stage 1: Plugin Upload

### API
```
POST /api/v1/plugins/upload
Content-Type: multipart/form-data

Body:
  - plugin_file: .py or .js file
  - metadata: JSON of tool definitions
```

### Example Request
```bash
curl -X POST http://localhost:8000/api/v1/plugins/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "plugin_file=@weather_tool.py" \
  -F 'metadata={"name": "weather", "version": "1.0.0"}'
```

### Metadata Format
```json
{
  "name": "weather",
  "version": "1.0.0",
  "tools": [
    {
      "name": "get_weather",
      "description": "Get current weather for a location",
      "parameters": {
        "location": {
          "type": "string",
          "description": "City name",
          "required": true
        }
      }
    }
  ]
}
```

---

## Stage 2: Plugin Validation

```python
# plugins/validator.py

async def validate_plugin(plugin_file, metadata) -> dict:
    """Validate plugin before registration"""
    
    errors = []
    
    # 1. Check tool definitions exist
    if not metadata.get("tools"):
        errors.append("No tools defined")
    
    # 2. Validate each tool
    for tool in metadata["tools"]:
        # Required fields
        if not tool.get("name"):
            errors.append("Tool missing name")
        if not tool.get("description"):
            errors.append(f"Tool {tool['name']} missing description")
        if not tool.get("parameters"):
            errors.append(f"Tool {tool['name']} missing parameters")
        
        # Parameter validation
        for param_name, param in tool["parameters"].items():
            if not param.get("type"):
                errors.append(f"Param {param_name} missing type")
    
    if errors:
        return {"valid": False, "errors": errors}
    
    return {"valid": True}
```

---

## Stage 3: Tool Registration

### Storage
```
Plugins stored in: /plugins/{plugin_id}/
├── __init__.py
├── tools.py          # Tool implementations
├── metadata.json    # Tool definitions
└── requirements.txt # Dependencies
```

### Registry Update
```python
# tools/registry.py

class ToolRegistry:
    def __init__(self):
        self.tools = {}
    
    async def register(self, metadata: dict, plugin_path: str):
        """Register tools from plugin"""
        
        for tool_def in metadata["tools"]:
            tool_id = f"{metadata['name']}.{tool_def['name']}"
            
            self.tools[tool_def["name"]] = {
                "id": tool_id,
                "name": tool_def["name"],
                "description": tool_def["description"],
                "parameters": tool_def["parameters"],
                "plugin_path": plugin_path,
                "enabled": True
            }
            
            print(f"Registered tool: {tool_id}")
    
    async def get_tool(self, name: str) -> dict:
        """Get tool by name"""
        return self.tools.get(name)
    
    async def list_tools(self) -> list:
        """List all available tools"""
        return [
            {"name": t["name"], "description": t["description"]}
            for t in self.tools.values()
            if t["enabled"]
        ]
```

---

## Stage 4: Hot Reload

### Orchestrator Refresh
```python
# orchestrator/plugins.py

async def refresh_tools():
    """Hot reload tools without restart"""
    
    async with httpx.AsyncClient() as client:
        # Get all tools from registry
        response = await client.get("http://tools:8005/tools")
        tools = response.json()["tools"]
    
    # Update local cache
    app.state.tool_registry = tools
    
    print(f"Reloaded {len(tools)} tools")

# Auto-refresh on plugin upload
@app.on_event("plugin_uploaded")
async def on_plugin_uploaded(event):
    await refresh_tools()
```

---

## Stage 5: Ready to Call

### Tool Execution
```python
# tools/executor.py

async def execute_tool(tool_name: str, params: dict) -> dict:
    """Execute a registered tool"""
    
    # 1. Get tool from registry
    tool = await registry.get_tool(tool_name)
    if not tool:
        return {"error": f"Tool {tool_name} not found"}
    
    # 2. Load plugin module
    plugin_path = tool["plugin_path"]
    module = importlib.import_module(f"plugins.{plugin_path}.tools")
    
    # 3. Execute tool function
    tool_func = getattr(module, tool_name)
    result = await tool_func(params)
    
    return {"status": "success", "result": result}
```

---

## Example Plugin

### File Structure
```
plugins/weather/
├── __init__.py
├── tools.py
├── metadata.json
└── requirements.txt
```

### tools.py
```python
# Weather tool implementation
import requests

async def get_weather(params: dict) -> dict:
    """Get weather for location"""
    
    location = params.get("location")
    api_key = params.get("api_key", "")
    
    response = requests.get(
        f"https://api.weather.com/v3/weather",
        params={"location": location, "apiKey": api_key}
    )
    
    data = response.json()
    
    return {
        "temperature": data["temperature"],
        "condition": data["condition"],
        "humidity": data["humidity"]
    }
```

### metadata.json
```json
{
  "name": "weather",
  "version": "1.0.0",
  "tools": [
    {
      "name": "get_weather",
      "description": "Get current weather for a location",
      "parameters": {
        "location": {
          "type": "string",
          "description": "City name (e.g., Tokyo, New York)",
          "required": true
        },
        "api_key": {
          "type": "string", 
          "description": "Weather API key (optional)",
          "required": false
        }
      }
    }
  ]
}
```

---

## Available Tools List

### GET /api/v1/tools
```bash
curl http://localhost:8000/api/v1/tools
```

**Response:**
```json
{
  "tools": [
    {
      "name": "get_weather",
      "description": "Get current weather for a location"
    },
    {
      "name": "send_message",
      "description": "Send a message to a contact"
    },
    {
      "name": "search_web",
      "description": "Search the web for information"
    }
  ]
}
```

---

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| Invalid plugin format | Not .py or .js | Use correct format |
| Missing metadata | No metadata.json | Include metadata |
| Duplicate tool | Tool already exists | Use version or rename |
| Execution error | Tool code error | Check tool logs |

---

## Security

### Sandboxed Execution
```python
# tools/sandbox.py

import subprocess
import tempfile

 async def execute_sandboxed(tool_name: str, params: dict) -> dict:
    """Execute tool in sandbox"""
    
    # Run in isolated process
    result = subprocess.run(
        ["python", "-c", f"from plugins.{tool_name} import run; print(run({params}))"],
        capture_output=True,
        timeout=10,  # 10 second timeout
        cwd="/sandbox"
    )
    
    if result.returncode != 0:
        return {"error": result.stderr.decode()}
    
    return {"result": result.stdout.decode()}
```

### Permission Model
```python
# tools/permissions.py

ALLOWED_MODULES = [
    "requests",
    "datetime",
    "json",
]

BLOCKED_PATTERNS = [
    "os.system",
    "subprocess.run",
    "open(",
    "exec(",
]
```

---

## Pipeline Summary

```
┌─────────────┐     POST /upload      ┌─────────────┐
│   Admin     │ ─────────────────────→ │   Gateway   │
│  (uploader) │                      │   (8000)    │
└─────────────┘                      └──────┬──────┘
                                             │
                                      Validate + Store
                                             │
                                             ▼
┌─────────────┐     GET /tools        ┌─────────────┐
│  Orchestrator│←──────────────────── │   Tools    │
│   (8002)    │    Hot reload       │   (8005)    │
└─────────────┘                      └─────────────┘
                                             │
                                      Register tools
                                             │
                                             ▼
┌─────────────┐                       ┌─────────────┐
│    Agent    │ ─────────────────────→│   Tools    │
│  (calls)    │   execute_tool()     │  (executes) │
└─────────────┘                       └─────────────┘
```

---

*Next: See [run-first-system.md](./run-first-system.md) to run it all*