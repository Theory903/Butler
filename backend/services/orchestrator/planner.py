from pydantic import BaseModel

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
        }

        steps = plan_templates.get(intent, [
            Step(action="memory_recall", params={}),
            Step(action="respond", params={"type": "general"}),
        ])

        return Plan(steps=steps, intent=intent, context=context)
