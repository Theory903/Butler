import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class A2UIBridgeService:
    """Agent-to-User Interface (A2UI) Bridge.

    Ported from OpenClaw's Canvas host, this service manages the
    communication bridge between the Butler backend and the frontend
    Canvas (WebView).
    """

    def inject_bridge_script(self, html: str) -> str:
        """Inject the OpenClaw-compatible bridge script into HTML."""
        snippet = """
<script>
(() => {
  // Cross-platform action bridge helper.
  // Works on:
  // - iOS: window.webkit.messageHandlers.openclawCanvasA2UIAction.postMessage(...)
  // - Android: window.openclawCanvasA2UIAction.postMessage(...)
  const handlerNames = ["openclawCanvasA2UIAction", "butlerCanvasAction"];

  function postToNode(payload) {
    try {
      const raw = typeof payload === "string" ? payload : JSON.stringify(payload);
      for (const name of handlerNames) {
        const iosHandler = globalThis.webkit?.messageHandlers?.[name];
        if (iosHandler && typeof iosHandler.postMessage === "function") {
          iosHandler.postMessage(raw);
          return true;
        }
        const androidHandler = globalThis[name];
        if (androidHandler && typeof androidHandler.postMessage === "function") {
          androidHandler.postMessage(raw);
          return true;
        }
      }
    } catch {}
    return false;
  }

  function sendUserAction(userAction) {
    const id = (userAction && typeof userAction.id === "string" && userAction.id.trim()) ||
               (globalThis.crypto?.randomUUID?.() ?? String(Date.now()));
    const action = { ...userAction, id };
    return postToNode({ userAction: action });
  }

  globalThis.OpenClaw = globalThis.OpenClaw ?? {};
  globalThis.OpenClaw.postMessage = postToNode;
  globalThis.OpenClaw.sendUserAction = sendUserAction;
  globalThis.openclawPostMessage = postToNode;
  globalThis.openclawSendUserAction = sendUserAction;

  // Butler extensions
  globalThis.Butler = globalThis.Butler ?? {};
  globalThis.Butler.sendAction = sendUserAction;

  console.log("[A2UI] Bridge initialized");
})();
</script>
"""
        if "</body>" in html:
            return html.replace("</body>", f"{snippet}</body>")
        return html + snippet

    def format_event_jsonl(self, events: list[dict[str, Any]]) -> str:
        """Format a list of events as a JSONL string."""
        return "\n".join(json.dumps(e) for e in events) + "\n"
