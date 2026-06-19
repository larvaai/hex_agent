"""LLM exposed as a capability — flows through execute_tool -> envelope + events like any tool. Epic E03/E04."""
from __future__ import annotations

from typing import Any

from core.kernel import AgentKernel
from core.schemas import FeatureDescriptor, ToolRequest
from llm.adapter import call_llm

FEATURE = FeatureDescriptor(
    name="llm",
    capabilities=("llm.chat",),
    description="LLM chat exposed as a tool capability so it is observed and disciplined like any tool.",
)


class LLMChatTool:
    name = "llm_chat_tool"

    def __init__(self, client: Any = None) -> None:
        self._client = client  # injectable for tests; None -> adapter's lazy module client

    def execute(self, request: ToolRequest) -> dict[str, Any]:
        a = request.args
        content = call_llm(
            a.get("messages", []),
            model=a.get("model"),
            temperature=a.get("temperature", 0.2),
            json_mode=a.get("json_mode", True),
            client=self._client,
        )
        return {"ok": True, "content": content, "model": a.get("model")}


def install(kernel: AgentKernel, *, client: Any = None) -> None:
    kernel.registry.register_feature(FEATURE)
    kernel.registry.register_tools(FEATURE.capabilities, LLMChatTool(client=client), feature_name=FEATURE.name)
