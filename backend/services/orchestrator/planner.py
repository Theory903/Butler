from pydantic import BaseModel
import structlog

logger = structlog.get_logger(__name__)

class Step(BaseModel):
    action: str
    params: dict

class Plan(BaseModel):
    steps: list[Step]
    intent: str
    context: dict

    def to_dict(self):
        return self.model_dump()

class PlanEngine:
    """Decompose intent into executable steps."""

    async def create_plan(self, intent: str, context: dict) -> Plan:
        """Create execution plan with ordered steps."""
        import json
        logger.warning("PLANNER_CREATE_PLAN", intent=intent, context=context)
        
        user_prompt = context.get("prompt", "") if context else ""
        logger.warning("PLANNER_USER_PROMPT", user_prompt=user_prompt[:100] if user_prompt else "")
        
        # Pattern-matched plans for known intents
        plan_templates = {
            "greeting": [Step(action="respond", params={"type": "greeting"})],
            "question": [
                Step(action="memory_recall", params={"type": "context"}),
                Step(action="respond", params={"type": "answer"}),
            ],
            "search": [
                Step(action="search_web", params={}),
                Step(action="extract_evidence", params={}),
                Step(action="respond", params={"type": "search_result"}),
            ],
            "tool_action": [
                Step(action="select_tool", params={}),
                Step(action="execute_tool", params={}),
                Step(action="verify_result", params={}),
                Step(action="respond", params={"type": "tool_result"}),
            ],
            "system_stats": [
                Step(action="system_stats", params={}),
                Step(action="respond", params={"type": "diagnostic_result"}),
            ],
        }

        steps = plan_templates.get(intent, [
            Step(action="memory_recall", params={"query": user_prompt}),
            Step(action="respond", params={"message": user_prompt}),
        ])
        
        # Also update template steps with message
        steps = [
            Step(action=s.action, params={**(s.params or {}), "message": user_prompt, "query": user_prompt})
            for s in steps
        ]
        
        logger.warning("PLANNER_STEPS", steps=[{"action": s.action, "params": str(s.params)[:100]} for s in steps])
        
        return Plan(steps=steps, intent=intent, context=context)
