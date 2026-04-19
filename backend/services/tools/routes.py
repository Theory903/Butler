"""Tools service - tool registry and execution."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Any, Dict

router = APIRouter(prefix="/tools", tags=["tools"])


class Tool(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    category: str


class ToolExecute(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]


TOOLS = [
    Tool(name="search_web", description="Search the web for information", parameters={"query": "string"}, category="search"),
    Tool(name="send_email", description="Send an email", parameters={"to": "string", "subject": "string", "body": "string"}, category="communication"),
    Tool(name="create_reminder", description="Create a reminder", parameters={"title": "string", "datetime": "string"}, category="productivity"),
    Tool(name="get_weather", description="Get weather for a location", parameters={"location": "string"}, category="information"),
]


@router.get("/", response_model=List[Tool])
async def list_tools():
    return TOOLS


@router.post("/execute")
async def execute_tool(req: ToolExecute):
    tool = next((t for t in TOOLS if t.name == req.tool_name), None)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {req.tool_name} not found")
    return {"result": f"Executed {req.tool_name} with params {req.parameters}", "success": True}


@router.get("/health")
async def health():
    return {"status": "healthy"}