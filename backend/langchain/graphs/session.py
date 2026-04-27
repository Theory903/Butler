"""Open-notebook Session Graphs.

Phase F.4: Open-notebook session graphs for conversation flow visualization.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SessionNode:
    """A node in the session graph."""

    node_id: str
    type: str  # user_message, agent_response, tool_call, etc.
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionEdge:
    """An edge in the session graph."""

    from_node: str
    to_node: str
    edge_type: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionGraph:
    """A graph representing a conversation session."""

    session_id: str
    nodes: dict[str, SessionNode] = field(default_factory=dict)
    edges: list[SessionEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: SessionNode) -> None:
        """Add a node to the graph."""
        self.nodes[node.node_id] = node

    def add_edge(self, edge: SessionEdge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        """Convert graph to dictionary."""
        return {
            "session_id": self.session_id,
            "nodes": {
                nid: {
                    "type": n.type,
                    "content": n.content,
                    "metadata": n.metadata,
                }
                for nid, n in self.nodes.items()
            },
            "edges": [
                {
                    "from": e.from_node,
                    "to": e.to_node,
                    "type": e.edge_type,
                    "metadata": e.metadata,
                }
                for e in self.edges
            ],
            "metadata": self.metadata,
        }


class SessionGraphBuilder:
    """Builder for open-notebook session graphs.

    This builder:
    - Constructs session graphs from conversation history
    - Tracks message flow and tool calls
    - Provides graph visualization data
    """

    def __init__(self):
        """Initialize the session graph builder."""
        self._graphs: dict[str, SessionGraph] = {}

    def create_graph(self, session_id: str) -> SessionGraph:
        """Create a new session graph.

        Args:
            session_id: Session identifier

        Returns:
            New session graph
        """
        graph = SessionGraph(session_id=session_id)
        self._graphs[session_id] = graph
        logger.info("session_graph_created", session_id=session_id)
        return graph

    def add_user_message(self, session_id: str, message_id: str, content: str) -> None:
        """Add a user message node.

        Args:
            session_id: Session identifier
            message_id: Message identifier
            content: Message content
        """
        graph = self._graphs.get(session_id)
        if not graph:
            return

        node = SessionNode(node_id=message_id, type="user_message", content=content)
        graph.add_node(node)

    def add_agent_response(self, session_id: str, message_id: str, content: str) -> None:
        """Add an agent response node.

        Args:
            session_id: Session identifier
            message_id: Message identifier
            content: Response content
        """
        graph = self._graphs.get(session_id)
        if not graph:
            return

        node = SessionNode(node_id=message_id, type="agent_response", content=content)
        graph.add_node(node)

    def add_tool_call(
        self, session_id: str, call_id: str, tool_name: str, args: dict[str, Any]
    ) -> None:
        """Add a tool call node.

        Args:
            session_id: Session identifier
            call_id: Call identifier
            tool_name: Tool name
            args: Tool arguments
        """
        graph = self._graphs.get(session_id)
        if not graph:
            return

        node = SessionNode(
            node_id=call_id,
            type="tool_call",
            content=f"Tool: {tool_name}",
            metadata={"tool_name": tool_name, "args": args},
        )
        graph.add_node(node)

    def add_edge(
        self, session_id: str, from_id: str, to_id: str, edge_type: str = "default"
    ) -> None:
        """Add an edge between nodes.

        Args:
            session_id: Session identifier
            from_id: Source node ID
            to_id: Target node ID
            edge_type: Edge type
        """
        graph = self._graphs.get(session_id)
        if not graph:
            return

        edge = SessionEdge(from_node=from_id, to_node=to_id, edge_type=edge_type)
        graph.add_edge(edge)

    def get_graph(self, session_id: str) -> SessionGraph | None:
        """Get a session graph.

        Args:
            session_id: Session identifier

        Returns:
            Session graph or None
        """
        return self._graphs.get(session_id)

    def remove_graph(self, session_id: str) -> None:
        """Remove a session graph.

        Args:
            session_id: Session identifier
        """
        if session_id in self._graphs:
            del self._graphs[session_id]
            logger.info("session_graph_removed", session_id=session_id)
