"""
Case 04 — build_kernel + install_configured_features (Plugin Factory ở quy mô hệ thống).

DISTILL TRUNG THỰC TỪ MÃ THẬT:
  - core/bootstrap.py:56-66       (build_kernel(config): dựng kernel rồi install features)
  - features/loader.py:10-25      (install_configured_features: import động + gọi module.install)
  - rag/feature.py:109-121        (install(kernel): mỗi feature tự đăng ký tool của mình)
  - features/llm_chat.py, features/example_echo.py (các module feature có install())
  - core/bootstrap.py:28-53       (_install_middleware: factory orchestrator bật/tắt theo config)

Đây là Factory Method "ở quy mô hệ thống": thay vì MỘT factory chọn MỘT kiểu cụ
thể, ta có một REGISTRY các hàm factory (mỗi feature/plugin một hàm install).
Loader đọc config['features'], import động từng module được bật, rồi gọi
module.install(kernel) — mỗi install() đóng vai factory tự đăng ký tool/capability
của feature đó vào kernel. 'Tạo gì' do config quyết định (late-binding).

Bản distill dùng stdlib. Lược bỏ: importlib + module thật (ta dùng registry hàm
trong cùng file để minh hoạ ý tưởng "mỗi feature một install factory"). Giữ
nguyên vai trò: dispatcher (loader) + concrete creators (install của mỗi feature)
+ chọn theo config + so sánh với kernel "nhồi cứng mọi tool".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


# ─────────────────────────────────────────────────────────────────────────────
# Hạ tầng fake: kernel + tool port (distill từ core/kernel.py + core/schemas.py)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ToolPort:
    """Một capability có thể gọi. Distill từ ToolPort/FeatureDescriptor."""

    name: str
    run: Callable[[dict], dict]


@dataclass
class FakeKernel:
    """Distill từ AgentKernel: giữ config + registry tool. Bỏ event/middleware nặng."""

    config: dict[str, Any]
    tools: dict[str, ToolPort] = field(default_factory=dict)
    installed_features: list[str] = field(default_factory=list)
    middleware: list[str] = field(default_factory=list)

    def register_tool(self, port: ToolPort) -> None:
        if port.name in self.tools:
            raise ValueError(f"Tool '{port.name}' already registered.")
        self.tools[port.name] = port

    def execute_tool(self, name: str, args: dict | None = None) -> dict:
        return self.tools[name].run(args or {})

    def use(self, mw_name: str) -> None:
        self.middleware.append(mw_name)


# ─────────────────────────────────────────────────────────────────────────────
# Mỗi FEATURE là một module có hàm install(kernel) — chính là factory của nó.
# (Trong mã thật: features/rag.py, features/llm_chat.py, features/example_echo.py)
# ─────────────────────────────────────────────────────────────────────────────
def install_echo(kernel: FakeKernel) -> None:
    """Distill ý tưởng features/example_echo.py.install — tự đăng ký tool echo."""
    kernel.register_tool(ToolPort("echo", lambda a: {"ok": True, "echo": a.get("text", "")}))
    kernel.installed_features.append("echo")


def install_llm_chat(kernel: FakeKernel) -> None:
    """Distill ý tưởng features/llm_chat.py.install — đăng ký tool chat (LLM fake)."""
    model = kernel.config.get("features", {}).get("llm_chat", {}).get("model", "fake-llm")
    kernel.register_tool(ToolPort("chat", lambda a: {"ok": True, "model": model,
                                                     "reply": f"[{model}] {a.get('prompt', '')}"}))
    kernel.installed_features.append("llm_chat")


def install_rag(kernel: FakeKernel) -> None:
    """Distill rag/feature.py:109-121.install — đăng ký 3 tool rag_* (nested factory)."""
    store: list[str] = []
    kernel.register_tool(ToolPort("rag_health", lambda a: {"ok": True, "count": len(store)}))
    kernel.register_tool(ToolPort("rag_ingest", lambda a: (store.append(a.get("doc", "")), {"ok": True})[1]))
    kernel.register_tool(ToolPort("rag_search", lambda a: {"ok": True,
                                                           "hits": [d for d in store if a.get("q", "") in d]}))
    kernel.installed_features.append("rag")


# REGISTRY các factory (một install function cho mỗi feature) — distill khái niệm
# "tên feature -> module" trong config. Loader sẽ tra registry này thay importlib.
FEATURE_INSTALLERS: dict[str, Callable[[FakeKernel], None]] = {
    "echo": install_echo,
    "llm_chat": install_llm_chat,
    "rag": install_rag,
}


# ─────────────────────────────────────────────────────────────────────────────
# Loader (dispatcher) — distill từ features/loader.py:10-25
# ─────────────────────────────────────────────────────────────────────────────
def install_configured_features(kernel: FakeKernel, config: dict[str, Any]) -> None:
    """Cài MỖI feature được bật trong config['features'].

    Mã thật dùng importlib.import_module(spec['module']) rồi getattr(module,'install').
    Ta thay bằng tra FEATURE_INSTALLERS — vẫn giữ ý 'late-binding theo config'.
    """
    features = config.get("features", {}) or {}
    for name, spec in features.items():
        spec = spec or {}
        if not spec.get("enabled", False):
            continue
        installer = FEATURE_INSTALLERS.get(name)
        if installer is None:
            raise ValueError(f"Feature '{name}' is enabled but has no installer.")
        installer(kernel)


def _install_middleware(kernel: FakeKernel, config: dict[str, Any]) -> None:
    """Distill từ core/bootstrap.py:28-53 — factory orchestrator bật/tắt theo config.
    Thứ tự ngoài->trong: timing, policy, retry, condense."""
    mw = config.get("middleware") or {}
    if (mw.get("timing") or {}).get("enabled"):
        kernel.use("TimingLog")
    if (mw.get("policy") or {}).get("enabled"):
        kernel.use("PolicyGate")
    if (mw.get("retry") or {}).get("enabled"):
        kernel.use("Retry")
    if (mw.get("condense") or {}).get("enabled"):
        kernel.use("CondenseResult")


def build_kernel(config: dict[str, Any]) -> FakeKernel:
    """Distill từ core/bootstrap.py:56-66."""
    kernel = FakeKernel(config=config)
    install_configured_features(kernel, config)
    _install_middleware(kernel, config)
    return kernel


# ─────────────────────────────────────────────────────────────────────────────
# ĐỐI CHỨNG: kernel "nhồi cứng" mọi tool (monolithic) — không plugin
# ─────────────────────────────────────────────────────────────────────────────
def build_monolithic_kernel() -> FakeKernel:
    """Anti-pattern: mọi tool nhồi cứng trong 1 hàm, không bật/tắt được theo config.

    Hậu quả: không thể chạy bản 'gọn' (chỉ echo) cho test; thêm feature = sửa hàm
    này; phụ thuộc nặng (vd qdrant) luôn bị kéo vào dù không dùng.
    """
    kernel = FakeKernel(config={})
    install_echo(kernel)
    install_llm_chat(kernel)
    install_rag(kernel)  # luôn bị kéo vào, kể cả khi không cần
    return kernel


def demo() -> None:
    print("=" * 72)
    print("CASE 04 — build_kernel + install_configured_features (Plugin Factory)")
    print("Nguồn thật: core/bootstrap.py:56-66 ; features/loader.py:10-25")
    print("=" * 72)

    print("\n[1] Config quyết định feature nào được nạp (late-binding).")
    cfg_min = {"features": {"echo": {"enabled": True},
                            "llm_chat": {"enabled": False},
                            "rag": {"enabled": False}}}
    k_min = build_kernel(cfg_min)
    print(f"    features bật = {k_min.installed_features}  tools = {sorted(k_min.tools)}")
    assert k_min.installed_features == ["echo"]
    assert set(k_min.tools) == {"echo"}, "chỉ feature được bật mới đăng ký tool"

    print("\n[2] Bật thêm rag + llm_chat qua config -> loader gọi đúng các install factory.")
    cfg_full = {"features": {"echo": {"enabled": True},
                             "llm_chat": {"enabled": True, "model": "fake-llm-v2"},
                             "rag": {"enabled": True}},
                "middleware": {"timing": {"enabled": True}, "retry": {"enabled": True}}}
    k_full = build_kernel(cfg_full)
    print(f"    features bật = {k_full.installed_features}")
    print(f"    tools = {sorted(k_full.tools)}")
    print(f"    middleware = {k_full.middleware}")
    assert {"echo", "chat", "rag_health", "rag_ingest", "rag_search"} <= set(k_full.tools)
    assert k_full.middleware == ["TimingLog", "Retry"]  # đúng thứ tự, chỉ cái được bật

    print("\n[3] Mỗi install() là factory riêng: rag tự đăng ký 3 tool (nested factory).")
    print(f"    k_full.execute_tool('chat', ...) = {k_full.execute_tool('chat', {'prompt': 'hi'})}")
    k_full.execute_tool("rag_ingest", {"doc": "alpha beta"})
    res = k_full.execute_tool("rag_search", {"q": "alpha"})
    print(f"    rag_search('alpha') = {res}")
    assert res["hits"] == ["alpha beta"]

    print("\n[4] MỞ RỘNG: thêm feature 'metrics' = đăng ký thêm 1 installer, KHÔNG sửa loader.")

    def install_metrics(kernel: FakeKernel) -> None:
        kernel.register_tool(ToolPort("metrics", lambda a: {"ok": True, "n_tools": len(kernel.tools)}))
        kernel.installed_features.append("metrics")

    FEATURE_INSTALLERS["metrics"] = install_metrics  # đăng ký plugin mới
    k_metrics = build_kernel({"features": {"echo": {"enabled": True}, "metrics": {"enabled": True}}})
    print(f"    features = {k_metrics.installed_features}  tools = {sorted(k_metrics.tools)}")
    assert "metrics" in k_metrics.tools
    print("    -> loader/build_kernel KHÔNG đổi 1 dòng. Open-Closed ở quy mô plugin.")

    print("\n[5] Feature bật nhưng không có installer -> báo lỗi rõ (features/loader.py:17-24).")
    try:
        build_kernel({"features": {"ghost": {"enabled": True}}})
        raise AssertionError("phải báo lỗi feature thiếu installer")
    except ValueError as e:
        print(f"    {e}")

    print("\n[6] ĐỐI CHỨNG — kernel nhồi cứng (monolithic):")
    mono = build_monolithic_kernel()
    print(f"    luôn nạp = {mono.installed_features}  (không thể chạy bản chỉ-echo cho test)")
    print("    -> phụ thuộc rag/qdrant bị kéo vào kể cả khi không dùng; thêm feature phải sửa hàm.")
    assert mono.installed_features == ["echo", "llm_chat", "rag"]

    print("\nKẾT LUẬN: hệ thống thật mở rộng Factory bằng REGISTRY các install factory")
    print("(một cho mỗi plugin). Config chọn nạp gì; loader chỉ điều phối; mỗi feature")
    print("tự dựng tool của mình. Thêm plugin = thêm 1 install, không đụng lõi.")
    print("\nTẤT CẢ ASSERT ĐỀU PASS.")


if __name__ == "__main__":
    demo()
