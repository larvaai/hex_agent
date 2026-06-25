"""Shared deterministic fixtures for the strict audit suite."""
from __future__ import annotations

import json
from typing import Any

import pytest
from hypothesis import HealthCheck, settings

from core.bootstrap import build_kernel
from features.llm_chat import FEATURE as LLM_FEATURE
from features.llm_chat import LLMChatTool


settings.register_profile(
    "audit",
    max_examples=100,
    deadline=None,
    derandomize=True,
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
settings.load_profile("audit")


@pytest.fixture(autouse=True)
def isolated_runtime_dirs(tmp_path, monkeypatch):
    """Every audit test gets isolated disk state and deterministic retry timing."""
    monkeypatch.setenv("AGENT_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("AGENT_WORKSPACE_DIR", str(tmp_path / "workspace"))
    monkeypatch.setenv("LLM_RETRY_BASE", "0")
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")


class ScriptedOpenAIClient:
    """Minimal OpenAI-compatible client with call recording and a strict script."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        outer = self

        class Completions:
            def create(self, **kwargs: Any):
                outer.calls.append(dict(kwargs))
                if not outer.responses:
                    raise AssertionError("Unexpected LLM call: scripted responses exhausted")
                item = outer.responses.pop(0)
                if isinstance(item, Exception):
                    raise item
                message = type("Message", (), {"content": item})()
                choice = type("Choice", (), {"message": message})()
                return type("Response", (), {"choices": [choice]})()

        self.chat = type("Chat", (), {"completions": Completions()})()


@pytest.fixture
def scripted_client():
    return ScriptedOpenAIClient


@pytest.fixture
def kernel_factory():
    def make(*responses: str | Exception, toolbox: bool = True, echo: bool = True):
        features: dict[str, dict[str, Any]] = {}
        if echo:
            features["example_echo"] = {"enabled": True, "module": "features.example_echo"}
        if toolbox:
            features["toolbox"] = {"enabled": True, "module": "toolbox.feature"}
        kernel = build_kernel({"features": features})
        if responses:
            client = ScriptedOpenAIClient(list(responses))
            kernel.registry.register_feature(LLM_FEATURE)
            kernel.registry.register_tools(
                LLM_FEATURE.capabilities,
                LLMChatTool(client=client),
                feature_name=LLM_FEATURE.name,
                kind="model",
                idempotent=True,
            )
            return kernel, client
        return kernel, None

    return make


def action(**fields: Any) -> str:
    return json.dumps(fields, ensure_ascii=False)
