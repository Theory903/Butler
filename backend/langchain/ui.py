"""Butler Generative UI and Functional API.

Provides UI components and functional API for LangChain agents.
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class UIComponent:
    """A UI component definition."""

    component_type: str  # "button", "input", "select", "card", etc.
    component_id: str
    label: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UIEvent:
    """A UI event."""

    event_type: str  # "click", "input", "submit", etc.
    component_id: str
    value: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FunctionalAPICall:
    """A functional API call definition."""

    function_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    return_type: str = "any"
    metadata: dict[str, Any] = field(default_factory=dict)


class ButlerGenerativeUI:
    """Generative UI system for LangChain agents.

    This system:
    - Generates UI components based on context
    - Handles UI events
    - Provides dynamic rendering
    - Supports streaming UI updates
    """

    def __init__(self):
        """Initialize the generative UI system."""
        self._components: dict[str, UIComponent] = {}
        self._event_handlers: dict[str, list[Any]] = {}

    def register_component(self, component: UIComponent) -> None:
        """Register a UI component.

        Args:
            component: UI component
        """
        self._components[component.component_id] = component
        logger.info("ui_component_registered", component_id=component.component_id)

    def get_component(self, component_id: str) -> UIComponent | None:
        """Get a component by ID.

        Args:
            component_id: Component ID

        Returns:
            UI component or None
        """
        return self._components.get(component_id)

    def generate_button(
        self,
        button_id: str,
        label: str,
        action: str,
        style: str = "primary",
    ) -> UIComponent:
        """Generate a button component.

        Args:
            button_id: Button ID
            label: Button label
            action: Action to perform
            style: Button style

        Returns:
            Button component
        """
        component = UIComponent(
            component_type="button",
            component_id=button_id,
            label=label,
            properties={
                "style": style,
                "action": action,
            },
            actions=[{"type": "click", "action": action}],
        )
        self.register_component(component)
        return component

    def generate_input(
        self,
        input_id: str,
        label: str,
        input_type: str = "text",
        placeholder: str = "",
    ) -> UIComponent:
        """Generate an input component.

        Args:
            input_id: Input ID
            label: Input label
            input_type: Input type
            placeholder: Placeholder text

        Returns:
            Input component
        """
        component = UIComponent(
            component_type="input",
            component_id=input_id,
            label=label,
            properties={
                "type": input_type,
                "placeholder": placeholder,
            },
            actions=[{"type": "input", "action": "update"}],
        )
        self.register_component(component)
        return component

    def generate_card(
        self,
        card_id: str,
        title: str,
        content: str,
        actions: list[dict[str, Any]] | None = None,
    ) -> UIComponent:
        """Generate a card component.

        Args:
            card_id: Card ID
            title: Card title
            content: Card content
            actions: Optional card actions

        Returns:
            Card component
        """
        component = UIComponent(
            component_type="card",
            component_id=card_id,
            label=title,
            properties={
                "content": content,
            },
            actions=actions or [],
        )
        self.register_component(component)
        return component

    def generate_form(
        self,
        form_id: str,
        fields: list[dict[str, Any]],
        submit_action: str,
    ) -> UIComponent:
        """Generate a form component.

        Args:
            form_id: Form ID
            fields: Form fields
            submit_action: Submit action

        Returns:
            Form component
        """
        component = UIComponent(
            component_type="form",
            component_id=form_id,
            properties={
                "fields": fields,
                "submit_action": submit_action,
            },
            actions=[{"type": "submit", "action": submit_action}],
        )
        self.register_component(component)
        return component

    def handle_event(self, event: UIEvent) -> Any:
        """Handle a UI event.

        Args:
            event: UI event

        Returns:
            Event handler result
        """
        handlers = self._event_handlers.get(event.component_id, [])
        results = []

        for handler in handlers:
            try:
                result = handler(event)
                results.append(result)
            except Exception:
                logger.exception("ui_event_handler_failed", component_id=event.component_id)

        return results

    def register_event_handler(self, component_id: str, handler: Any) -> None:
        """Register an event handler.

        Args:
            component_id: Component ID
            handler: Handler function
        """
        if component_id not in self._event_handlers:
            self._event_handlers[component_id] = []
        self._event_handlers[component_id].append(handler)

    def get_ui_state(self) -> dict[str, Any]:
        """Get the current UI state.

        Returns:
            UI state dictionary
        """
        return {
            "components": {
                comp_id: {
                    "type": comp.component_type,
                    "label": comp.label,
                    "properties": comp.properties,
                }
                for comp_id, comp in self._components.items()
            },
            "component_count": len(self._components),
        }

    def clear_components(self) -> None:
        """Clear all components."""
        self._components.clear()
        self._event_handlers.clear()
        logger.info("ui_components_cleared")


class ButlerFunctionalAPI:
    """Functional API for LangChain agents.

    This API:
    - Defines callable functions
    - Handles function execution
    - Provides function discovery
    - Supports function streaming
    """

    def __init__(self):
        """Initialize the functional API."""
        self._functions: dict[str, FunctionalAPICall] = {}
        self._function_handlers: dict[str, Any] = {}

    def register_function(
        self,
        function_name: str,
        handler: Any,
        description: str = "",
        parameters: dict[str, Any] | None = None,
        return_type: str = "any",
    ) -> None:
        """Register a function.

        Args:
            function_name: Function name
            handler: Handler function
            description: Function description
            parameters: Function parameters schema
            return_type: Return type
        """
        func_call = FunctionalAPICall(
            function_name=function_name,
            parameters=parameters or {},
            description=description,
            return_type=return_type,
        )
        self._functions[function_name] = func_call
        self._function_handlers[function_name] = handler
        logger.info("functional_api_function_registered", function_name=function_name)

    def get_function(self, function_name: str) -> FunctionalAPICall | None:
        """Get a function by name.

        Args:
            function_name: Function name

        Returns:
            Function call or None
        """
        return self._functions.get(function_name)

    async def call_function(
        self,
        function_name: str,
        parameters: dict[str, Any],
    ) -> Any:
        """Call a function.

        Args:
            function_name: Function name
            parameters: Function parameters

        Returns:
            Function result
        """
        handler = self._function_handlers.get(function_name)
        if not handler:
            raise ValueError(f"Function not found: {function_name}")

        logger.info("functional_api_function_called", function_name=function_name)

        if callable(handler):
            return await handler(**parameters)
        return handler

    async def call_function_stream(
        self,
        function_name: str,
        parameters: dict[str, Any],
    ) -> AsyncIterator[Any]:
        """Call a function with streaming.

        Args:
            function_name: Function name
            parameters: Function parameters

        Yields:
            Streaming results
        """
        handler = self._function_handlers.get(function_name)
        if not handler:
            raise ValueError(f"Function not found: {function_name}")

        logger.info("functional_api_function_streaming", function_name=function_name)

        # If handler is async generator, yield from it
        if hasattr(handler, "__aiter__"):
            async for result in handler(**parameters):
                yield result
        else:
            # Otherwise, yield single result
            result = await self.call_function(function_name, parameters)
            yield result

    def list_functions(self) -> list[FunctionalAPICall]:
        """List all registered functions.

        Returns:
            List of function calls
        """
        return list(self._functions.values())

    def get_function_schema(self, function_name: str) -> dict[str, Any] | None:
        """Get function schema.

        Args:
            function_name: Function name

        Returns:
            Function schema or None
        """
        func = self._functions.get(function_name)
        if not func:
            return None

        return {
            "name": func.function_name,
            "description": func.description,
            "parameters": func.parameters,
            "return_type": func.return_type,
        }

    def get_all_schemas(self) -> dict[str, dict[str, Any]]:
        """Get all function schemas.

        Returns:
            Dictionary of function schemas
        """
        schemas = {}
        for func_name in self._functions.keys():
            schema = self.get_function_schema(func_name)
            if schema is not None:
                schemas[func_name] = schema
        return schemas


class ButlerUIAPI:
    """Combined UI and Functional API.

    This system:
    - Combines generative UI and functional API
    - Provides unified interface
    - Supports UI-driven function calls
    - Handles function-generated UI
    """

    def __init__(self):
        """Initialize the UI API system."""
        self._ui = ButlerGenerativeUI()
        self._api = ButlerFunctionalAPI()

    @property
    def ui(self) -> ButlerGenerativeUI:
        """Get the generative UI system."""
        return self._ui

    @property
    def api(self) -> ButlerFunctionalAPI:
        """Get the functional API."""
        return self._api

    async def execute_ui_action(self, action: str, parameters: dict[str, Any]) -> Any:
        """Execute a UI action via functional API.

        Args:
            action: Action name
            parameters: Action parameters

        Returns:
            Action result
        """
        return await self.api.call_function(action, parameters)

    def generate_ui_from_function(
        self,
        function_name: str,
    ) -> UIComponent | None:
        """Generate UI for a function.

        Args:
            function_name: Function name

        Returns:
            Generated UI component or None
        """
        func = self.api.get_function(function_name)
        if not func:
            return None

        # Generate form based on function parameters
        fields = []
        for param_name, param_schema in func.parameters.items():
            fields.append(
                {
                    "name": param_name,
                    "label": param_name.replace("_", " ").title(),
                    "type": param_schema.get("type", "text"),
                    "required": param_schema.get("required", False),
                }
            )

        return self.ui.generate_form(
            form_id=f"form_{function_name}",
            fields=fields,
            submit_action=function_name,
        )

    def get_combined_state(self) -> dict[str, Any]:
        """Get combined UI and API state.

        Returns:
            Combined state dictionary
        """
        return {
            "ui": self.ui.get_ui_state(),
            "api": {
                "functions": [f.function_name for f in self.api.list_functions()],
                "function_count": len(self.api._functions),
            },
        }

    def clear_all(self) -> None:
        """Clear all UI and API state."""
        self.ui.clear_components()
        self.api._functions.clear()
        self.api._function_handlers.clear()
        logger.info("ui_api_cleared")
