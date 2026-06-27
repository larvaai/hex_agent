"""Anti-pattern: GLOBAL MUTABLE STATE (+ Cargo Cult Singleton + Premature Optimization)
— distill từ hex_agent.

NGUỒN THẬT (đã mở file kiểm chứng):
  - llm/adapter.py:9      -> _client: Any = None        (biến module-level, mutable, dùng chung)
  - llm/adapter.py:25-32  -> _get_client(): lazy-init một instance OpenAI DUY NHẤT, cache
                             vào _client toàn cục, chia sẻ cho mọi lời gọi.
  - llm/adapter.py:35-37  -> reset_client(): mutate _client = None (đường thoát duy nhất;
                             dễ quên gọi trong test).
  - llm/adapter.py:72-77  -> call_llm(): dùng `client if client is not None else _get_client()`
                             — có cửa DI (tham số client) nhưng mặc định vẫn rơi về global.

BỆNH LÝ NÃO (Lesson 33, mục 1.3.c — Loss of diversity): cocaine addiction ép mọi reward
(food/sex/social) dồn về MỘT đường dopamine spike, mất khả năng phân biệt sub-system.
Ở code: mọi call_llm dồn về MỘT _client chung, không cách ly được cấu hình/đời sống.
Cộng thêm mục 1.3.d (Wrong timing — Premature Optimization): cache toàn cục để "tiết kiệm"
chi phí import/khởi tạo, trong khi chi phí đó không đáng kể còn chi phí coupling thì cao.

Ý TƯỞNG ĐỐI CHỨNG: hai "test" chạy đồng thời, mỗi test cần một client cấu hình khác nhau
(base_url khác). Với GLOBAL mutable, test thứ hai vô tình DÙNG client của test thứ nhất
(vì _client đã được cache) -> interference, kết quả sai. Với FACTORY/DI, mỗi caller nhận
instance riêng -> isolation phục hồi.

CHỈ DÙNG STDLIB. Hạ tầng nặng (openai, network) thay bằng FakeClient tối thiểu chỉ mang
một nhãn base_url để nhận diện "đây là client của ai".
"""
from __future__ import annotations

import threading
from typing import Optional


# ── FakeClient: thay cho openai.OpenAI, chỉ giữ đủ để nhận diện danh tính ──────────
class FakeClient:
    """Đóng vai openai.OpenAI(base_url=...). Mỗi instance nhớ base_url của nó để ta
    chứng minh được 'call này dùng client của cấu hình nào'."""

    _created_count = 0  # đếm số instance từng được tạo, để kiểm chứng caching

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        FakeClient._created_count += 1

    def chat(self, prompt: str) -> str:
        # "Phản hồi" mã hoá base_url => caller biết đã gọi tới endpoint nào.
        return f"[{self.base_url}] reply to {prompt!r}"


# ════════════════════════════════════════════════════════════════════════════════
# PHIÊN BẢN "XẤU" — global mutable singleton, distill llm/adapter.py:9, 25-37, 72-77
# ════════════════════════════════════════════════════════════════════════════════

_client: Optional[FakeClient] = None  # distill adapter.py:9 — global mutable


def _get_client(base_url: str = "http://localhost:1234/v1") -> FakeClient:
    """Distill adapter.py:25-32 — lazy-init MỘT instance, cache toàn cục.

    LƯU Ý CHỖ HỎNG: base_url chỉ được đọc Ở LẦN ĐẦU TIÊN. Mọi caller sau đó nhận lại
    đúng instance cũ, BẤT KỂ họ truyền base_url khác.
    """
    global _client
    if _client is None:
        _client = FakeClient(base_url=base_url)  # lazy import + lazy init trong code thật
    return _client


def reset_client() -> None:
    """Distill adapter.py:35-37 — đường thoát duy nhất, dễ quên gọi."""
    global _client
    _client = None


def call_llm_global(prompt: str, *, base_url: str) -> str:
    """Distill adapter.py:72-77 — mặc định rơi về global _client."""
    active = _get_client(base_url)
    return active.chat(prompt)


# ════════════════════════════════════════════════════════════════════════════════
# PHIÊN BẢN "TỐT" — factory / dependency injection, không state toàn cục
# ════════════════════════════════════════════════════════════════════════════════


def make_client(base_url: str) -> FakeClient:
    """Factory: 'lazy' đúng nghĩa = hoãn việc tạo tới khi cần, nhưng trả INSTANCE MỚI
    mỗi lần — không chia sẻ state toàn cục. Caller tự quyết vòng đời."""
    return FakeClient(base_url=base_url)


def call_llm_di(prompt: str, *, client: FakeClient) -> str:
    """Dependency injection: client được TRUYỀN VÀO, không lấy từ global.
    Mỗi caller cách ly hoàn toàn cấu hình của mình."""
    return client.chat(prompt)


# ── kịch bản đối chứng: hai luồng chạy đồng thời với cấu hình khác nhau ────────────


def _run_concurrent(call, configs: list[str], results: dict[str, str]) -> None:
    """Chạy `call` trên nhiều luồng, mỗi luồng một base_url, gom kết quả."""
    barrier = threading.Barrier(len(configs))  # ép các luồng vào cùng thời điểm

    def worker(idx: int, base_url: str) -> None:
        barrier.wait()  # đồng bộ để tối đa hoá khả năng đua nhau
        results[f"worker-{idx}"] = call(idx, base_url)

    threads = [threading.Thread(target=worker, args=(i, b)) for i, b in enumerate(configs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def demo() -> None:
    print("=" * 76)
    print("CASE 02 — GLOBAL MUTABLE CLIENT (Cargo Cult Singleton) trong llm/adapter.py")
    print("=" * 76)

    CONFIG_A = "http://server-A:1234/v1"
    CONFIG_B = "http://server-B:5678/v1"

    # ── (A) Bản GLOBAL: hai caller, hai cấu hình khác nhau ───────────────────────
    print("\n--- (A) Bản GLOBAL mutable (giống adapter.py) ---")
    reset_client()
    FakeClient._created_count = 0

    # Caller 1 yêu cầu server-A, caller 2 yêu cầu server-B.
    reply_a = call_llm_global("ping", base_url=CONFIG_A)
    reply_b = call_llm_global("ping", base_url=CONFIG_B)
    print("    Caller 1 (muốn server-A) nhận:", reply_a)
    print("    Caller 2 (muốn server-B) nhận:", reply_b)
    print("    Số FakeClient được tạo:", FakeClient._created_count)
    print("    => Caller 2 BỊ ROUTE NHẦM sang server-A! _client cache lần đầu thắng.")
    print("       Một instance chia sẻ mãi mãi = loss of diversity (mọi call → 1 đường).")

    # Bất biến của anti-pattern: chỉ 1 instance tồn tại, caller 2 không được phục vụ đúng.
    assert FakeClient._created_count == 1, "global cache chỉ tạo đúng 1 instance"
    assert CONFIG_A in reply_b and CONFIG_B not in reply_b, (
        "bằng chứng route nhầm: caller 2 nhận đúng endpoint của caller 1"
    )

    # ── (B) Bản DI/factory: cùng hai caller, cách ly hoàn toàn ────────────────────
    print("\n--- (B) Bản FACTORY / Dependency Injection ---")
    FakeClient._created_count = 0
    client_a = make_client(CONFIG_A)
    client_b = make_client(CONFIG_B)
    reply_a2 = call_llm_di("ping", client=client_a)
    reply_b2 = call_llm_di("ping", client=client_b)
    print("    Caller 1 (server-A) nhận:", reply_a2)
    print("    Caller 2 (server-B) nhận:", reply_b2)
    print("    Số FakeClient được tạo:", FakeClient._created_count)
    print("    => Mỗi caller dùng đúng endpoint của mình. Isolation phục hồi.")

    assert CONFIG_A in reply_a2 and CONFIG_B in reply_b2, "DI: mỗi caller đúng endpoint"
    assert FakeClient._created_count == 2, "DI tạo một instance riêng cho mỗi cấu hình"

    # ── Đối chứng dưới ĐỒNG THỜI (threads) — vì sao global lại nguy hiểm hơn ──────
    print("\n--- (C) Dưới đồng thời: hai test chạy song song, cấu hình khác nhau ---")

    print("    [GLOBAL] hai luồng đua nhau init _client:")
    reset_client()
    FakeClient._created_count = 0
    res_global: dict[str, str] = {}
    _run_concurrent(
        lambda idx, base: call_llm_global(f"req-{idx}", base_url=base),
        [CONFIG_A, CONFIG_B],
        res_global,
    )
    distinct_endpoints_global = {r.split("]")[0] + "]" for r in res_global.values()}
    print("        kết quả:", res_global)
    print("        endpoint thực sự dùng:", distinct_endpoints_global)
    # Bất biến: với global, dù có 2 cấu hình, MỌI luồng dồn về <=1 endpoint (kẻ init đầu).
    assert len(distinct_endpoints_global) == 1, (
        "global: mọi luồng dồn về một endpoint duy nhất — test không cách ly"
    )

    print("    [DI] hai luồng, mỗi luồng client riêng:")
    FakeClient._created_count = 0
    res_di: dict[str, str] = {}
    clients = {0: make_client(CONFIG_A), 1: make_client(CONFIG_B)}
    _run_concurrent(
        lambda idx, base: call_llm_di(f"req-{idx}", client=clients[idx]),
        [CONFIG_A, CONFIG_B],
        res_di,
    )
    distinct_endpoints_di = {r.split("]")[0] + "]" for r in res_di.values()}
    print("        kết quả:", res_di)
    print("        endpoint thực sự dùng:", distinct_endpoints_di)
    assert len(distinct_endpoints_di) == 2, "DI: hai luồng giữ đúng hai endpoint riêng"

    print("\n[OK] Mọi assert qua. Bài học: 'lazy' ≠ 'global + mutable'.")
    print("     Lazy đúng = hoãn tạo tới khi cần (factory). Global cache = coupling +")
    print("     mất isolation test + Premature Optimization (cache thứ không cần cache).")
    print("=" * 76)


if __name__ == "__main__":
    demo()
