from collections.abc import Callable

from app.tools.analysis import StructuredAnalysis
from app.tools.calculator import Calculator


class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, Callable] = {}
        self.register("analysis", StructuredAnalysis().run)
        self.register("calculator", Calculator().calculate)

    def register(self, name: str, tool: Callable) -> None:
        if name in self.tools:
            raise ValueError(f"Tool already registered: {name}")
        self.tools[name] = tool

    def get(self, name: str) -> Callable:
        if name not in self.tools:
            raise KeyError(f"Unknown tool: {name}")
        return self.tools[name]
