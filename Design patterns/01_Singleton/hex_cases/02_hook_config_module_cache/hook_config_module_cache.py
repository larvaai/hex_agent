"""
Singleton (Creational) — Hook Runtime Config, cache mức module (lazy + memoize).

BẢN DISTILL TRUNG THỰC từ code thật trong hex_agent:
  - harness/hooks/hook_runtime.py:162      -> `_config_cache = None  # None = not yet loaded`
  - harness/hooks/hook_runtime.py:172-191  -> `_load_config()` (lazy load + cache 1 lần/process)
  - harness/hooks/hook_runtime.py:177      -> `if _config_cache is not None: return _config_cache`
  - harness/hooks/hook_runtime.py:187-190  -> Exception -> {} + log, KHÔNG ném lỗi (robust)
  - harness/hooks/hook_runtime.py:194-197  -> `_reset_config_cache()` (test seam)

Ý đồ thiết kế (theo comment trong source thật):
  - Config YAML của hook chỉ nên đọc + parse ĐÚNG MỘT lần mỗi process. Hook được gọi
    rất nhiều lần; nếu mỗi lần đều mở file + parse YAML thì vừa chậm vừa lãng phí.
  - `_config_cache` = None nghĩa là "chưa nạp". Lần đầu nạp; các lần sau trả cache.
    Đây chính là Singleton kiểu Pythonic nhất: module-level state, không cần __new__.
  - Config hỏng (YAML lỗi / thiếu thư viện) => trả {} + ghi log, KHÔNG ném exception.
    Ranh giới Singleton phải vững: một config xấu không được làm sập một hook.
  - `_reset_config_cache()` là test seam để đọc lại file mới.

File này KHÔNG import yaml / hex_agent. Ta thay:
  - việc đọc file YAML thật bằng một "nguồn config giả" đếm số lần đọc đĩa (read_count).
  - việc parse YAML hỏng bằng cờ `corrupt` làm hàm parse ném ValueError.
Tất cả chỉ dùng thư viện chuẩn.
"""
from __future__ import annotations


# --------------------------------------------------------------------------- #
# HẠ TẦNG GIẢ — thay cho file YAML thật trên đĩa.                              #
# read_count đếm số lần "chạm đĩa": Singleton đúng phải giữ con số này = 1     #
# dù gọi _load_config() bao nhiêu lần đi nữa.                                  #
# --------------------------------------------------------------------------- #
class FakeConfigSource:
    """Giả lập file config YAML trên đĩa.

    - `present`: file có tồn tại không (mô phỏng p.is_file()).
    - `corrupt`: nội dung hỏng -> parse ném lỗi (mô phỏng yaml hỏng).
    - `read_count`: đếm số lần thực sự đọc + parse (để chứng minh chỉ 1 lần).
    """

    def __init__(self, data: dict, *, present: bool = True, corrupt: bool = False) -> None:
        self._data = data
        self.present = present
        self.corrupt = corrupt
        self.read_count = 0

    def is_file(self) -> bool:
        return self.present

    def parse(self) -> dict:
        """Mô phỏng read_text() + yaml.safe_load(). Tăng read_count mỗi lần chạm."""
        self.read_count += 1
        if self.corrupt:
            raise ValueError("YAML khong hop le (mo phong config hong)")
        return dict(self._data)


# Nguồn config "trên đĩa" dùng cho demo. Trong code thật đây là file
# harness/hooks/.../config.yaml resolved off __file__.
_config_source = FakeConfigSource(
    {"telemetry": {"enabled": True, "mode": "advisory"}},
)


# Mô phỏng log_hook_error(): config hỏng chỉ ghi log, không ném ra ngoài.
_crash_log: list[str] = []


def log_hook_error(where: str, exc: Exception) -> None:
    """Tương đương harness/hooks/hook_runtime.py:188 — ghi log, nuốt lỗi."""
    _crash_log.append(f"[{where}] {type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# SINGLETON — distill tu harness/hooks/hook_runtime.py                         #
# --------------------------------------------------------------------------- #

# Vai trò: "instance holder" mức module. None = chưa nạp.
# Tương đương hook_runtime.py:162  `_config_cache = None`
_config_cache: dict | None = None


def _load_config() -> dict:
    """Loader idempotent + điểm truy cập. Parse ĐÚNG MỘT lần mỗi process.

    Tương đương hook_runtime.py:172-191.
    - Nếu đã có cache -> trả ngay (không chạm đĩa).         (line 177)
    - Nếu chưa -> đọc nguồn, cache lại.                     (line 184-190)
    - Nếu hỏng -> {} + log, KHÔNG ném lỗi.                  (line 187-189)
    """
    global _config_cache
    if _config_cache is not None:                 # hook_runtime.py:177
        return _config_cache
    cfg: dict = {}
    try:
        if _config_source.is_file():              # hook_runtime.py:182
            cfg = _config_source.parse()          # hook_runtime.py:183-184 (lazy parse)
    except Exception as e:                         # hook_runtime.py:187
        log_hook_error("hook_runtime", e)         # hook_runtime.py:188
        cfg = {}                                   # hook_runtime.py:189
    _config_cache = cfg                            # hook_runtime.py:190
    return cfg                                     # hook_runtime.py:191


def _reset_config_cache() -> None:
    """Test seam: bỏ cache để lần gọi sau đọc lại file mới.

    Tương đương hook_runtime.py:194-197.
    """
    global _config_cache
    _config_cache = None


# --------------------------------------------------------------------------- #
# DEMO                                                                         #
# --------------------------------------------------------------------------- #
def demo() -> None:
    global _config_source
    print("=" * 70)
    print("SINGLETON — Hook Config Cache (lazy+memoize) — hook_runtime.py")
    print("=" * 70)

    # Bước 0: chưa gọi -> cache là None, chưa chạm đĩa lần nào.
    print("\n[Buoc 0] Sau khi import, truoc khi goi:")
    print(f"   _config_cache = {_config_cache}, read_count = {_config_source.read_count}")
    assert _config_cache is None and _config_source.read_count == 0

    # Bước 1: gọi _load_config() ba lần -> chỉ đọc đĩa ĐÚNG 1 lần.
    print("\n[Buoc 1] Ba hook khac nhau cung goi _load_config():")
    c1 = _load_config()   # lần đầu -> chạm đĩa
    c2 = _load_config()   # trả cache
    c3 = _load_config()   # trả cache
    print(f"   ket qua giong nhau: {c1 == c2 == c3}")
    print(f"   read_count (so lan parse YAML) = {_config_source.read_count}")
    assert c1 == c2 == c3, "Ba lan goi phai tra cung config"
    assert _config_source.read_count == 1, "Chi duoc parse DUNG MOT lan"
    assert _config_cache is not None, "Sau lan dau, cache phai duoc dien"
    print("   => assert PASS: YAML chi bi doc/parse 1 lan du goi 3 lan.")

    # Bước 2: reset_config_cache() (test seam) -> lần gọi sau đọc lại file.
    print("\n[Buoc 2] Goi _reset_config_cache() (mo phong test doc file moi):")
    _reset_config_cache()
    print(f"   sau reset: _config_cache = {_config_cache}")
    assert _config_cache is None, "reset phai dat cache ve None"
    _load_config()
    print(f"   sau khi goi lai: read_count = {_config_source.read_count}")
    assert _config_source.read_count == 2, "Sau reset, file duoc doc lai"
    print("   => assert PASS: reset cho phep nap lai config moi.")

    # Bước 3: ROBUST — config HỎNG phải trả {} + log, KHÔNG sập hook.
    print("\n[Buoc 3] Config HONG (YAML loi) — Singleton phai chiu loi:")
    _config_source = FakeConfigSource({}, corrupt=True)  # nguồn mới: hỏng
    _reset_config_cache()                                 # bỏ cache cũ
    crashes_before = len(_crash_log)
    result = _load_config()   # KHÔNG được ném exception
    print(f"   _load_config() tra ve: {result!r}")
    print(f"   so dong crash-log moi: {len(_crash_log) - crashes_before}")
    assert result == {}, "Config hong phai tra {} (hook_runtime.py:189)"
    assert len(_crash_log) == crashes_before + 1, "Phai ghi 1 dong log loi"
    print("   => assert PASS: config xau -> {} + log, hook van song.")

    # ĐỐI CHỨNG: nếu KHÔNG cache (đọc mỗi lần), 100 hook = 100 lần parse đĩa.
    print("\n[DOI CHUNG] Neu KHONG cache (parse moi lan goi):")
    fresh = FakeConfigSource({"a": 1})
    for _ in range(100):
        fresh.parse()  # mô phỏng: mỗi hook tự parse, không memoize
    print(f"   100 hook -> {fresh.read_count} lan parse YAML (lang phi I/O).")
    assert fresh.read_count == 100, "Khong cache => parse lai moi lan"
    print("   So sanh: Singleton chi parse 1 lan cho ca process.")

    print("\n" + "=" * 70)
    print("KET LUAN: module-level cache = Singleton Pythonic nhat (khong can __new__).")
    print("Lazy + memoize tiet kiem I/O; {} -on-error giu ranh gioi Singleton vung chac.")
    print("=" * 70)


if __name__ == "__main__":
    demo()
