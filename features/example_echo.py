"""Example feature — an echo tool used by smoke/tests and as the plugin pattern. Epic E01."""
from __future__ import annotations

from typing import Any

from core.kernel import AgentKernel
from core.schemas import FeatureDescriptor, ToolRequest

FEATURE = FeatureDescriptor(
    name="example_echo",
    capabilities=("echo",),
    description="Trivial echo tool used by smoke tests and as a feature-plugin example.",
)


class EchoTool:
    name = "echo_tool"

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        return {"ok": True, "echo": dict(request.args)}


def install(kernel: AgentKernel) -> None:
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tools(FEATURE.capabilities, EchoTool(), feature_name=FEATURE.name)
