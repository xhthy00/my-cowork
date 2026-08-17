from langchain_core.tools import BaseTool


class ToolRegistry:
    """Lightweight registry for LangChain tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, name: str, tool: BaseTool) -> None:
        """Register a tool under a dotted name."""
        self._tools[name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool if present."""
        self._tools.pop(name, None)

    def unregister_prefix(self, prefix: str) -> list[str]:
        """Remove all tools whose dotted name starts with *prefix*."""
        removed = [n for n in self._tools if n.startswith(prefix)]
        for n in removed:
            del self._tools[n]
        return removed

    def get(self, name: str) -> BaseTool:
        """Retrieve a tool by dotted name."""
        if name not in self._tools:
            raise KeyError(f"Tool {name!r} is not registered")
        return self._tools[name]

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def list_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def list_by_prefix(self, prefix: str) -> list[BaseTool]:
        return [t for n, t in self._tools.items() if n.startswith(prefix)]
