"""Build a kernel and install features + middleware from config. Epic E01/E06."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.events import EventBus
from core.kernel import AgentKernel
from core.registry import CapabilityRegistry

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


def _install_middleware(kernel: AgentKernel, config: dict[str, Any]) -> None:
    """Wire built-in stateless middleware declared under config['middleware'].
    Order = outer -> inner: timing, policy, retry, condense. Inert if the section is absent.
    BudgetGuard is intentionally NOT wired here: its same-tool counter is per-run, so a
    kernel-lifetime instance would leak across runs — wire it per run instead."""
    mw = config.get("middleware") or {}
    if (mw.get("timing") or {}).get("enabled"):
        from middleware import TimingLog

        kernel.use(TimingLog())
    policy = mw.get("policy") or {}
    if policy.get("enabled"):
        from middleware import PolicyGate

        kernel.use(PolicyGate(deny=set(policy.get("deny") or ())))
    retry = mw.get("retry") or {}
    if retry.get("enabled"):
        from middleware import Retry

        kernel.use(Retry(attempts=int(retry.get("attempts", 2))))
    condense = mw.get("condense") or {}
    if condense.get("enabled"):
        from middleware import CondenseResult

        kernel.use(CondenseResult(max_chars=int(condense.get("max_chars", 2000)),
                                  max_list=int(condense.get("max_list", 10))))


def build_kernel(config: dict[str, Any]) -> AgentKernel:
    kernel = AgentKernel(
        registry=CapabilityRegistry(),
        events=EventBus(),
        config=config,
    )
    from features.loader import install_configured_features

    install_configured_features(kernel, config)
    _install_middleware(kernel, config)
    return kernel


def create_kernel(config_path: str | Path | None = None) -> AgentKernel:
    return build_kernel(load_config(config_path))
