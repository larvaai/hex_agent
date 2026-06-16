"""Install the features that are enabled in config['features']. Epic E01."""
from __future__ import annotations

import importlib
from typing import Any

from core.kernel import AgentKernel


def install_configured_features(kernel: AgentKernel, config: dict[str, Any]) -> None:
    """Install each enabled feature declared in config['features']."""
    features = config.get("features", {}) or {}
    for name, spec in features.items():
        spec = spec or {}
        if not spec.get("enabled", False):
            continue
        module_path = spec.get("module")
        if not module_path:
            raise ValueError(f"Feature '{name}' is enabled but has no 'module'.")
        module = importlib.import_module(module_path)
        install = getattr(module, "install", None)
        if install is None:
            raise ValueError(f"Feature module '{module_path}' has no install(kernel).")
        install(kernel)
