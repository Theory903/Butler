import json
import importlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ButlerIntegrationRuntime:
    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4-20250514",
        base_url: str = "https://api.anthropic.com/v1",
        max_iterations: int = 100,
    ):
        self.model = model
        self.base_url = base_url
        self.max_iterations = max_iterations
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                openai_module = importlib.import_module("openai")
                openai_client = getattr(openai_module, "OpenAI")
                self._client = openai_client(base_url=self.base_url, api_key="placeholder")
            except Exception as e:
                logger.warning("Could not initialize client: %s", e)
        return self._client

    async def process(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        """Process a conversation turn with tool calling.

        Returns dict with:
        - response: the assistant message
        - tool_calls: any tool calls made
        - usage: token usage info
        """
        if not messages:
            return {"error": "No messages provided"}

        try:
            client = self._get_client()
            if client is None:
                return {"response": "Model not configured", "tool_calls": []}

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools or [],
                max_tokens=4096,
            )

            return {
                "response": response.choices[0].message.content,
                "tool_calls": getattr(response.choices[0].message, "tool_calls", None),
                "usage": getattr(response, "usage", None),
            }
        except Exception as e:
            logger.exception("Error processing message: %s", e)
            return {"error": str(e), "tool_calls": []}

    async def run_conversation(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Simple interface - returns final response string."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        result = await self.process(messages)
        return result.get("response", result.get("error", "No response"))


# Backward-compatible alias while Butler-facing wrappers migrate to the
# Butler-owned name.
HermesAIAgentRuntime = ButlerIntegrationRuntime
