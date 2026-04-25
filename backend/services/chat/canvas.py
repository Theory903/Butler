"""Canvas Render - Rich chat UI rendering like OpenCLAW."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CanvasSurface(StrEnum):
    ASSISTANT_MESSAGE = "assistant_message"
    USER_MESSAGE = "user_message"
    TOOL_RESULT = "tool_result"
    SYSTEM_MESSAGE = "system_message"


class CanvasRenderType(StrEnum):
    URL = "url"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    CODE = "code"
    MARKDOWN = "markdown"
    TABLE = "table"
    FILE = "file"
    MAP = "map"
    CALENDAR = "calendar"
    CONTACT = "contact"
    LOCATION = "location"


@dataclass
class CanvasPreview:
    kind: str = "canvas"
    surface: CanvasSurface = CanvasSurface.ASSISTANT_MESSAGE
    render: CanvasRenderType = CanvasRenderType.URL
    title: str | None = None
    preferred_height: int | None = None
    url: str | None = None
    view_id: str | None = None
    class_name: str | None = None
    style: str | None = None


@dataclass
class CanvasRender:
    @staticmethod
    def parse_url_metadata(url: str) -> dict[str, Any]:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        domain = parsed.netloc

        previews = {
            "youtube": {"render": "video", "domain": "youtube.com"},
            "vimeo": {"render": "video", "domain": "vimeo.com"},
            "github": {"render": "code", "domain": "github.com"},
            "figma": {"render": "design", "domain": "figma.com"},
            "maps": {"render": "map", "domain": "google.com/maps"},
        }

        for name, config in previews.items():
            if config["domain"] in domain:
                return {"render": config["render"], "title": name.title()}

        return {"render": "url", "title": domain}

    @staticmethod
    def render_url(url: str, title: str | None = None) -> CanvasPreview:
        """Render URL as rich preview."""
        metadata = CanvasRender.parse_url_metadata(url)
        return CanvasPreview(
            surface=CanvasSurface.ASSISTANT_MESSAGE,
            render=CanvasRenderType(metadata["render"]),
            title=title or metadata.get("title", url),
            url=url,
        )

    @staticmethod
    def render_image(url: str, alt: str = "", width: int | None = None) -> CanvasPreview:
        return CanvasPreview(
            surface=CanvasSurface.ASSISTANT_MESSAGE,
            render=CanvasRenderType.IMAGE,
            title=alt or "Image",
            url=url,
            preferred_height=width,
        )

    @staticmethod
    def render_code(code: str, language: str = "python") -> dict[str, Any]:
        return {
            "kind": "code",
            "language": language,
            "code": code,
            "surface": CanvasSurface.TOOL_RESULT,
        }

    @staticmethod
    def render_table(headers: list[str], rows: list[list[str]]) -> dict[str, Any]:
        return {
            "kind": "table",
            "headers": headers,
            "rows": rows,
            "surface": CanvasSurface.TOOL_RESULT,
        }

    @staticmethod
    def render_markdown(content: str) -> dict[str, Any]:
        return {
            "kind": "markdown",
            "content": content,
            "surface": CanvasSurface.ASSISTANT_MESSAGE,
        }


@dataclass
class ToolContent:
    @staticmethod
    def parse_tool_result(result: dict[str, Any]) -> dict[str, Any]:
        """Parse and render tool execution results."""
        tool_name = result.get("tool", "")
        success = result.get("success", True)
        output = result.get("output", "")
        error = result.get("error")

        content = {
            "tool": tool_name,
            "success": success,
            "output": output,
        }

        if error:
            content["error"] = error
            content["render"] = "error"
        elif output:
            content["render"] = "result"

        if "url" in output:
            content["preview"] = CanvasRender.render_url(output)

        return content

    @staticmethod
    def format_action_result(action: dict[str, Any]) -> str:
        action_type = action.get("type", "")
        result = action.get("result", {})

        if action_type == "search":
            return f"🔍 Found {result.get('count', 0)} results"
        if action_type == "write":
            return f"✍️ Wrote {result.get('lines', 0)} lines"
        if action_type == "execute":
            return f"⚡ Executed: {result.get('command', '')}"
        if action_type == "browse":
            return f"🌐 Visited: {result.get('url', '')}"

        return f"✅ {action_type}"


from typing import Union

Union = Union
