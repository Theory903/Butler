import json
from domain.ml.contracts import IntentClassifierContract, IntentResult

class IntentClassifier(IntentClassifierContract):
    """Tiered intent classification: fast patterns → lightweight ML → full model.
    
    Implements escalation to T2 (vLLM) and T3 (Cloud) for complex intents.
    """
    
    # T0: Pattern matching (zero latency)
    PATTERN_INTENTS = {
        "greeting": ["hello", "hi", "hey", "good morning", "good evening"],
        "farewell": ["bye", "goodbye", "see you", "talk later"],
        "thanks": ["thank you", "thanks", "appreciate it"],
        "help": ["help", "what can you do", "how do you work"],
        "status": ["what's happening", "status update", "any updates"],
    }
    
    def __init__(self, runtime=None):
        self._runtime = runtime
    
    async def classify(self, text: str) -> IntentResult:
        # T0: Regex/pattern match
        t0_result = self._pattern_match(text)
        if t0_result and t0_result.confidence >= 0.9:
            t0_result.tier = "T0"
            return t0_result
        
        # T1: Lightweight keyword classifier
        t1_result = self._keyword_classify(text)
        if t1_result and t1_result.confidence >= 0.8:
            t1_result.tier = "T1"
            return t1_result
        
        # T2/T3: LLM Refinement if runtime is available
        if self._runtime:
            return await self._llm_classify(text, fallback=t1_result)
        
        # Fallback if no runtime
        res = t1_result or IntentResult(
            label="general",
            confidence=0.5,
            complexity="simple",
            requires_tools=False,
            requires_memory=True,
        )
        res.tier = "T1"
        return res
    
    def _pattern_match(self, text: str) -> IntentResult | None:
        text_lower = text.lower().strip()
        for intent, patterns in self.PATTERN_INTENTS.items():
            if any(p in text_lower for p in patterns):
                return IntentResult(label=intent, confidence=0.95, complexity="simple", tier="T0")
        return None
    
    def _keyword_classify(self, text: str) -> IntentResult | None:
        keywords = {
            "search": (["search", "find", "look up", "what is", "who is"], "search", True),
            "weather": (["weather", "temperature", "forecast"], "search", True),
            "reminder": (["remind", "reminder", "don't forget"], "tool_action", True),
            "send": (["send", "email", "message", "text"], "tool_action", True),
            "schedule": (["schedule", "calendar", "meeting"], "tool_action", True),
            "remember": (["remember", "note", "save"], "memory_write", False),
        }
        
        text_lower = text.lower()
        for intent, (kws, complexity, needs_tools) in keywords.items():
            if any(kw in text_lower for kw in kws):
                return IntentResult(
                    label=intent, confidence=0.75, complexity=complexity,
                    requires_tools=needs_tools, requires_memory=True, tier="T1"
                )
        return None

    async def _llm_classify(self, text: str, fallback: IntentResult | None) -> IntentResult:
        """Use LLM (T2/T3) to classify and extract entities."""
        prompt = f"""Classify intent and extract entities from: "{text}"
        Return JSON: {{
            "label": "string",
            "confidence": float,
            "complexity": "simple|complex",
            "requires_tools": bool,
            "entities": [{{ "type": "string", "value": "string" }}]
        }}
        """
        try:
            # Default to T2 (local) for intent refinement
            res = await self._runtime.execute_inference("local_reasoning_qwen3", {"prompt": prompt})
            if res["status"] == "success":
                data = json.loads(res["generated_text"])
                return IntentResult(
                    label=data["label"],
                    confidence=data["confidence"],
                    complexity=data["complexity"],
                    requires_tools=data["requires_tools"],
                    requires_memory=True,
                    tier="T2",
                    entities=data.get("entities", [])
                )
        except Exception:
            pass
            
        return fallback or IntentResult(label="general", confidence=0.5, complexity="complex", tier="T2")
