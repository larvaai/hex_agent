"""
Singleton (Creational) — Module-Level LLM Client, khởi tạo lười (lazy).

BẢN DISTILL TRUNG THỰC từ code thật trong hex_agent:
  - llm/adapter.py:9      ->  `_client: Any = None`  (biến giữ instance, mức module)
  - llm/adapter.py:25-32  ->  `_get_client()`        (điểm truy cập, factory idempotent)
  - llm/adapter.py:35-37  ->  `reset_client()`       (test seam: đặt lại về None)
  - llm/adapter.py:72-90  ->  `call_llm(... client=None)` (cho phép inject client để test)
  - tests_audit/test_llm_features_rigor.py:62-70 -> fixture autouse reset Singleton
  - tests_audit/test_llm_features_rigor.py:78     -> assert `adapter._client is None`

Ý đồ thiết kế (theo comment trong source thật):
  - `_client` là None khi chưa dùng; chỉ tạo OpenAI() thật sự ở LẦN GỌI ĐẦU TIÊN
    (lazy init) -> không dùng mạng lúc import, không tốn constructor nếu không cần.
  - Module Python chỉ import 1 lần mỗi process => `_client` bền vững qua mọi lời gọi
    => mọi nơi `_get_client()` đều nhận CÙNG MỘT object (single source of truth).
  - `reset_client()` là "test seam": vì Singleton là kẻ thù lớn nhất của unit test,
    ta phải có cách xóa state global để mỗi test bắt đầu sạch.

File này KHÔNG import openai / hex_agent. Ta thay OpenAI() nặng bằng một fake
`FakeOpenAIClient` tối thiểu chỉ dùng thư viện chuẩn (đếm số lần kết nối).
"""
from __future__ import annotations

import itertools


# --------------------------------------------------------------------------- #
# HẠ TẦNG GIẢ (fake) — thay cho `from openai import OpenAI`                     #
# Trong code thật, đây là một kết nối mạng đắt tiền (TCP + auth). Ở đây ta chỉ #
# mô phỏng: mỗi lần "tạo client" là một lần tốn tài nguyên, có id() riêng.     #
# --------------------------------------------------------------------------- #
_connection_counter = itertools.count(1)


class FakeOpenAIClient:
    """Giả lập OpenAI() — mô phỏng một tài nguyên tốn kém (kết nối mạng).

    Mỗi lần khởi tạo = một kết nối mới (so_ket_noi tăng). Trong Singleton đúng,
    ta chỉ được tạo ĐÚNG MỘT lần cho cả process.
    """

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.connection_id = next(_connection_counter)  # vai trò: "handle mạng"
        print(f"   [HA TANG] Mo ket noi MOI toi {base_url} "
              f"(connection_id={self.connection_id}, id={id(self):#x})")

    def chat(self, prompt: str) -> str:
        return f"(tra loi tu connection #{self.connection_id}) echo: {prompt}"


# --------------------------------------------------------------------------- #
# SINGLETON — distill tu llm/adapter.py                                        #
# --------------------------------------------------------------------------- #

# Vai trò: "instance holder" — biến mức module, None = chưa khởi tạo.
# Tương đương llm/adapter.py:9  `_client: Any = None`
_client: FakeOpenAIClient | None = None


def _defaults() -> dict:
    """Tương đương llm/adapter.py:13-22 (rút gọn): cấu hình đọc từ env/default."""
    return {"base_url": "http://localhost:1234/v1"}


def _get_client() -> FakeOpenAIClient:
    """Điểm truy cập toàn cục + factory idempotent (lazy init).

    Tương đương llm/adapter.py:25-32. Lần đầu: tạo client và lưu vào `_client`.
    Các lần sau: trả về đúng object đã có. Không tạo lại.
    """
    global _client
    if _client is None:                       # adapter.py:27
        cfg = _defaults()
        _client = FakeOpenAIClient(cfg["base_url"])   # adapter.py:31 (lazy construct)
    return _client                            # adapter.py:32


def reset_client() -> None:
    """Test seam — đặt lại Singleton về chưa-khởi-tạo.

    Tương đương llm/adapter.py:35-37. Bắt buộc phải có vì Singleton là global state;
    không có cái này thì các unit test sẽ "lây nhiễm" state cho nhau.
    """
    global _client
    _client = None


def call_llm(prompt: str, *, client: FakeOpenAIClient | None = None) -> str:
    """Distill llm/adapter.py:72-90 (rút gọn): cho phép INJECT client.

    Nếu caller truyền `client`, dùng nó (không dùng Singleton, tốt cho test).
    Nếu không, lấy từ Singleton qua `_get_client()`.
    """
    active = client if client is not None else _get_client()   # adapter.py:77
    return active.chat(prompt)


# --------------------------------------------------------------------------- #
# ĐỐI CHỨNG — khi KHÔNG dùng Singleton                                         #
# --------------------------------------------------------------------------- #
def _build_client_no_singleton() -> FakeOpenAIClient:
    """Mỗi "module" tự tạo client riêng — KHÔNG memoize. Đây là cách SAI:
    mở N kết nối cho N nơi gọi, lãng phí tài nguyên và có thể mâu thuẫn state.
    """
    return FakeOpenAIClient(_defaults()["base_url"])


# --------------------------------------------------------------------------- #
# DEMO                                                                         #
# --------------------------------------------------------------------------- #
def demo() -> None:
    print("=" * 70)
    print("SINGLETON — Module-Level LLM Client (lazy) — distill tu llm/adapter.py")
    print("=" * 70)

    # Bước 0: vừa import xong, Singleton phải là None (lazy: chưa tốn kết nối nào).
    print("\n[Buoc 0] Sau khi 'import', truoc khi goi:")
    print(f"   _client = {_client}  -> chua co ket noi nao duoc mo (lazy init).")
    assert _client is None, "Lazy init: khong duoc tao client luc import"

    # Bước 1: ba 'module' khác nhau cùng gọi _get_client() -> phải cùng 1 object.
    print("\n[Buoc 1] Ba module (vision/memory/instinct) cung xin client:")
    c_vision = _get_client()      # lần đầu -> tạo thật
    c_memory = _get_client()      # tái dùng
    c_instinct = _get_client()    # tái dùng
    print(f"   vision  -> id={id(c_vision):#x}")
    print(f"   memory  -> id={id(c_memory):#x}")
    print(f"   instinct-> id={id(c_instinct):#x}")
    assert c_vision is c_memory is c_instinct, "Phai la CUNG MOT instance"
    assert c_vision.connection_id == 1, "Chi duoc mo dung 1 ket noi"
    print("   => assert PASS: ca ba nhan CUNG MOT object, chi 1 ket noi duoc mo.")

    # Bước 2: gọi call_llm() vài lần -> vẫn dùng lại đúng kết nối đó.
    print("\n[Buoc 2] Goi call_llm() hai lan (di qua Singleton):")
    print("   ", call_llm("xin chao"))
    print("   ", call_llm("ban khoe khong"))
    assert _client is c_vision, "Van la Singleton cu, khong tao moi"
    print("   => assert PASS: khong mo them ket noi nao.")

    # Bước 3: reset_client() (test seam) -> lần gọi sau tạo OBJECT MỚI.
    print("\n[Buoc 3] Goi reset_client() (mo phong teardown giua hai test):")
    reset_client()
    print(f"   sau reset: _client = {_client}")
    assert _client is None, "reset_client() phai dat _client ve None"  # giống test:78
    c_after = _get_client()       # tạo lại -> connection_id mới
    print(f"   xin lai client -> id={id(c_after):#x}, connection_id={c_after.connection_id}")
    assert c_after is not c_vision, "Sau reset phai la OBJECT KHAC"
    assert c_after.connection_id == 2, "Ket noi moi sau khi reset"
    print("   => assert PASS: reset cho phep test bat dau voi state sach.")

    # Bước 4: inject client -> KHÔNG dùng Singleton, KHÔNG làm bẩn cache module.
    print("\n[Buoc 4] Inject client rieng vao call_llm() (duong test thuan):")
    before = _client
    injected = FakeOpenAIClient("http://test-fake/v1")
    print("   ", call_llm("ping", client=injected))
    assert _client is before, "Inject khong duoc lam ban Singleton (giong test:82)"
    print("   => assert PASS: cache module khong bi dong vao khi inject.")

    # ĐỐI CHỨNG: nếu KHÔNG dùng Singleton, ba module mở ba kết nối.
    print("\n[DOI CHUNG] Neu moi module tu tao client (KHONG Singleton):")
    a = _build_client_no_singleton()
    b = _build_client_no_singleton()
    d = _build_client_no_singleton()
    ids = {a.connection_id, b.connection_id, d.connection_id}
    print(f"   ba lan goi -> ba connection_id khac nhau: {sorted(ids)}")
    assert a is not b and b is not d, "Khong Singleton => ba object khac nhau"
    assert len(ids) == 3, "Lang phi: ba ket noi cho cung mot viec"
    print("   => Hau qua: lang phi tai nguyen + nguy co state phan manh.")

    print("\n" + "=" * 70)
    print("KET LUAN: 1 instance + global access (lazy) = Single Source of Truth.")
    print("reset_client() la cai gia bat buoc de Singleton song chung voi unit test.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
