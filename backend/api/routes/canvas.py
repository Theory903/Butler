import logging
from fastapi import APIRouter, Depends, Response
from fastapi.responses import HTMLResponse
from core.deps import get_a2ui_bridge
from services.gateway.a2ui_bridge import A2UIBridgeService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["canvas"])

@router.get("/canvas", response_class=HTMLResponse)
async def get_canvas(
    service: A2UIBridgeService = Depends(get_a2ui_bridge)
):
    """Serve the A2UI Canvas with the bridge injected."""
    # In a real implementation, this would load a template or static file.
    # For now, we'll serve a basic HTML shell with the bridge.
    html_content = """
<!DOCTYPE html>
<html>
<head>
    <title>Butler Canvas</title>
    <style>
        body { font-family: sans-serif; background: #0f172a; color: white; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .container { text-align: center; border: 1px solid #334155; padding: 2rem; border-radius: 12px; }
        button { background: #3b82f6; color: white; border: none; padding: 0.5rem 1rem; border-radius: 6px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Butler Canvas</h1>
        <p>A2UI Bridge active.</p>
        <button onclick="OpenClaw.sendUserAction({ type: 'click', target: 'test-button' })">Test Action</button>
    </div>
</body>
</html>
"""
    injected_html = service.inject_bridge_script(html_content)
    return Response(content=injected_html, media_type="text/html")
