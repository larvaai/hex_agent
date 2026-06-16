"""Build a kernel and install features from config/features.yaml. Epic E01."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.events import EventBus
from core.kernel import AgentKernel
from core.registry import CapabilityRegistry
from core.state import StateStore

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config" / "features.yaml"


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        return {"features": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Feature config must be a mapping: {path}")
    data.setdefault("features", {})
    return data


def build_kernel(config: dict[str, Any]) -> AgentKernel:
    kernel = AgentKernel(
        registry=CapabilityRegistry(),
        events=EventBus(),
        state=StateStore(),
        config=config,
    )
    from features.loader import install_configured_features

    install_configured_features(kernel, config)
    return kernel


def create_kernel(config_path: str | Path | None = None) -> AgentKernel:
    return build_kernel(load_config(config_path))
