"""
Case 04 — Composition Root: Feature Bootstrap (Wiring Adapters into Core).

Bản DISTILL trung thực của COMPOSITION ROOT trong Clean Architecture của hex_agent.
Clean Architecture cho phép ĐÚNG MỘT chỗ (composition root) import mọi vòng — nơi outer
gặp inner. hex_agent phân tán composition qua build_kernel + feature installer + bootstrap
subsystem. Config-driven lazy loading: tắt feature -> KHÔNG import adapter của nó.

Nguồn thật trong hex_agent (đã mở kiểm chứng):
  - core/bootstrap.py:56-66   -> build_kernel(): composition root, gọi install_configured_features + middleware
  - features/loader.py:10-25  -> install_configured_features(): lazy import module theo config, gọi install(kernel)
  - features/llm_chat.py:17-37 -> LLMChatTool adapter + install(kernel) đăng ký tool vào registry
  - core/registry.py:43-122   -> CapabilityRegistry (registry application, freeze, resolve)
  - delegation/bootstrap.py:13-24 -> composition root subsystem khác, cùng pattern

Chỉ dùng standard library. importlib + module thật được thay bằng một "module registry"
trong-tiến-trình + bộ đếm import để CHỨNG MINH lazy loading mà không cần file ngoài.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


# ─────────────────────────────────────────────────────────────────────────────
# VÒNG 1 — ENTITY mô tả feature (core/schemas.py FeatureDescriptor).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class FeatureDescriptor:
    """Distill core/schemas.py:114-129."""
    name: str
    capabilities: tuple[str, ...] = ()
    description: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# VÒNG 2 — APPLICATION REGISTRY (core/registry.py:43-122). Lõi quản tool, freeze, resolve.
# ─────────────────────────────────────────────────────────────────────────────
class NullToolPort:
    """Distill core/registry.py:29-40. Giữ kernel sống khi tool thiếu."""
    name = "null_tool"

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "tool": request.get("name"),
                "error": f"No tool capability registered for '{request.get('name')}'."}


class CapabilityRegistry:
    """Distill core/registry.py:43-122 (rút gọn)."""

    def __init__(self) -> None:
        self._tools: dict[str, Any] = {}
        self._features: dict[str, FeatureDescriptor] = {}
        self._null = NullToolPort()
        self._frozen = False

    def _ensure_mutable(self) -> None:
        if self._frozen:
            raise RuntimeError("Capability registry is frozen for active sessions.")

    def freeze(self) -> None:
        self._frozen = True

    def register_feature(self, descriptor: FeatureDescriptor) -> None:
        self._ensure_mutable()
        self._features[descriptor.name] = descriptor

    def register_tool(self, name: str, executor: Any) -> None:
        self._ensure_mutable()
        self._tools[name] = executor

    def resolve_tool(self, name: str) -> Any:
        return self._tools.get(name, self._null)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def list_features(self) -> list[str]:
        return sorted(self._features)


@dataclass
class AgentKernel:
    """Distill core/kernel.py (rút gọn): chỉ giữ registry + config cho ví dụ composition."""
    registry: CapabilityRegistry
    config: dict[str, Any] = field(default_factory=dict)

    def execute_tool(self, name: str) -> dict[str, Any]:
        return self.registry.resolve_tool(name).execute({"name": name})


# ─────────────────────────────────────────────────────────────────────────────
# "MODULE REGISTRY" thay cho importlib + filesystem.
# Mỗi 'module' đứng thay một file feature thật (features/llm_chat.py, rag/feature.py...).
# _IMPORT_COUNTS đếm số lần một module THỰC SỰ bị nạp -> chứng minh lazy loading.
# ─────────────────────────────────────────────────────────────────────────────
_IMPORT_COUNTS: dict[str, int] = {}
_MODULE_REGISTRY: dict[str, Callable[[], "FeatureModule"]] = {}


@dataclass
class FeatureModule:
    """Một module feature: có FEATURE descriptor + hàm install(kernel) (như features/llm_chat.py)."""
    feature: FeatureDescriptor
    install: Callable[[AgentKernel], None]


def import_module(path: str) -> FeatureModule:
    """Distill ý nghĩa importlib.import_module trong features/loader.py:20.
    Tăng bộ đếm để ta thấy module nào THỰC SỰ được nạp."""
    if path not in _MODULE_REGISTRY:
        raise ModuleNotFoundError(f"No module: {path}")
    _IMPORT_COUNTS[path] = _IMPORT_COUNTS.get(path, 0) + 1
    return _MODULE_REGISTRY[path]()


# ── Adapter + feature module: LLM chat (distill features/llm_chat.py:17-37) ──
def _make_llm_module() -> FeatureModule:
    FEATURE = FeatureDescriptor(name="llm", capabilities=("llm.chat",),
                                description="LLM chat exposed as a tool capability.")

    class LLMChatTool:  # adapter implement port tool (features/llm_chat.py:17-32)
        name = "llm_chat_tool"
        def execute(self, request: dict[str, Any]) -> dict[str, Any]:
            return {"ok": True, "content": "[fake-llm] xin chào", "model": "local-model"}

    def install(kernel: AgentKernel) -> None:  # features/llm_chat.py:35-37
        kernel.registry.register_feature(FEATURE)
        for cap in FEATURE.capabilities:
            kernel.registry.register_tool(cap, LLMChatTool())

    return FeatureModule(FEATURE, install)


# ── Adapter + feature module: RAG, có dep NẶNG giả lập (distill rag/feature.py) ──
def _make_rag_module() -> FeatureModule:
    FEATURE = FeatureDescriptor(name="rag", capabilities=("rag.search",),
                                description="Local RAG over a vector store.")

    # Đây là dep nặng (giả lập qdrant_client). Việc import_module('features.rag') nạp module này;
    # nếu RAG bị tắt trong config, dòng dưới KHÔNG bao giờ chạy -> không kéo theo dep nặng.
    _IMPORT_COUNTS["__heavy_qdrant__"] = _IMPORT_COUNTS.get("__heavy_qdrant__", 0) + 1

    class RagSearchTool:
        name = "rag_search"
        def execute(self, request: dict[str, Any]) -> dict[str, Any]:
            return {"ok": True, "hits": []}

    def install(kernel: AgentKernel) -> None:
        kernel.registry.register_feature(FEATURE)
        kernel.registry.register_tool("rag.search", RagSearchTool())

    return FeatureModule(FEATURE, install)


_MODULE_REGISTRY["features.llm_chat"] = _make_llm_module
_MODULE_REGISTRY["features.rag"] = _make_rag_module


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITION — feature loader (features/loader.py:10-25). Lazy: chỉ nạp feature ENABLED.
# ─────────────────────────────────────────────────────────────────────────────
def install_configured_features(kernel: AgentKernel, config: dict[str, Any]) -> None:
    """Distill features/loader.py:10-25."""
    features = config.get("features", {}) or {}
    for name, spec in features.items():
        spec = spec or {}
        if not spec.get("enabled", False):
            continue  # <- feature tắt: KHÔNG import module -> không kéo theo adapter/dep của nó
        module_path = spec.get("module")
        if not module_path:
            raise ValueError(f"Feature '{name}' is enabled but has no 'module'.")
        module = import_module(module_path)        # lazy import theo config
        module.install(kernel)                      # adapter tự đăng ký vào registry


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSITION ROOT (core/bootstrap.py:56-66). Nơi DUY NHẤT thấy mọi vòng.
# ─────────────────────────────────────────────────────────────────────────────
def build_kernel(config: dict[str, Any]) -> AgentKernel:
    """Distill core/bootstrap.py:56-66."""
    kernel = AgentKernel(registry=CapabilityRegistry(), config=config)
    install_configured_features(kernel, config)   # wire adapter vào core theo config
    # (bản thật còn _install_middleware ở đây — lược cho gọn)
    return kernel


# ─────────────────────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────────────────────
def _reset_counts() -> None:
    _IMPORT_COUNTS.clear()


def demo() -> None:
    print("=" * 74)
    print("CASE 04 — Composition Root: Feature Bootstrap trong hex_agent")
    print("=" * 74)

    print("\n[1] Config bật llm, TẮT rag. build_kernel chỉ nạp adapter được bật.")
    _reset_counts()
    config_a = {"features": {
        "llm": {"enabled": True, "module": "features.llm_chat"},
        "rag": {"enabled": False, "module": "features.rag"},
    }}
    kernel_a = build_kernel(config_a)
    print("    tools đã đăng ký:", kernel_a.registry.list_tools())
    print("    features:", kernel_a.registry.list_features())
    print("    import counts:", dict(_IMPORT_COUNTS))
    print("    -> 'features.rag' KHÔNG được import; dep nặng qdrant KHÔNG bị kéo theo.")
    print("    gọi llm.chat:", kernel_a.execute_tool("llm.chat"))
    print("    gọi rag.search (chưa cài) -> NullToolPort:", kernel_a.execute_tool("rag.search"))

    print("\n[2] Bật cả hai feature. Giờ 'features.rag' MỚI được import (lazy).")
    _reset_counts()
    config_b = {"features": {
        "llm": {"enabled": True, "module": "features.llm_chat"},
        "rag": {"enabled": True, "module": "features.rag"},
    }}
    kernel_b = build_kernel(config_b)
    print("    tools:", kernel_b.registry.list_tools())
    print("    import counts:", dict(_IMPORT_COUNTS))
    print("    -> chỉ KHI rag enabled, '__heavy_qdrant__' mới xuất hiện trong counts.")

    print("\n[3] Composition root là nơi DUY NHẤT thấy cả config lẫn adapter.")
    print("    Use case (registry) KHÔNG biết feature nào tồn tại đến khi bootstrap wire vào.")

    print("\n[4] Sau khi build, freeze registry -> không thể thêm tool giữa run.")
    kernel_b.registry.freeze()
    try:
        kernel_b.registry.register_tool("late", object())
    except RuntimeError as exc:
        print("    đăng ký SAU freeze bị chặn:", exc)

    # ── ASSERT: bất biến của pattern ──
    # (a) Feature tắt -> module KHÔNG được import -> dep nặng không bị kéo theo.
    _reset_counts()
    build_kernel(config_a)
    assert "features.rag" not in _IMPORT_COUNTS
    assert "__heavy_qdrant__" not in _IMPORT_COUNTS
    # (b) Feature bật -> module được import đúng một lần -> dep nặng xuất hiện.
    _reset_counts()
    k = build_kernel(config_b)
    assert _IMPORT_COUNTS.get("features.rag") == 1
    assert _IMPORT_COUNTS.get("__heavy_qdrant__") == 1
    # (c) Tool thiếu -> NullToolPort, kernel KHÔNG crash (graceful fallback).
    kbad = build_kernel({"features": {}})
    res = kbad.execute_tool("khong_ton_tai")
    assert res["ok"] is False and "No tool capability" in res["error"]
    # (d) freeze chặn mutate sau khi composition xong.
    k.registry.freeze()
    try:
        k.registry.register_tool("x", object())
    except RuntimeError:
        pass
    else:
        raise AssertionError("register_tool sau freeze phải raise")
    # (e) Composition root thấy mọi vòng: build_kernel nhận config VÀ wire adapter.
    assert k.registry.has_tool("llm.chat") and k.registry.has_tool("rag.search")

    print("\n[OK] Mọi assert qua. Composition root = nơi duy nhất import mọi vòng; config-driven lazy.")


if __name__ == "__main__":
    demo()
