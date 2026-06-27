# -*- coding: utf-8 -*-
"""
Lesson 09 — Decorator Pattern
Ví dụ neuroscience: myelin sheath wrap axon để tăng tốc dẫn truyền 50-100x
qua saltatory conduction (nhảy giữa Nodes of Ranvier). Cùng axon, cùng signal,
cùng neurotransmitter — chỉ thêm decorator wrap.

MS (Multiple Sclerosis) = remove decorator → conduction velocity rớt 10-20x.
Aδ-fiber (myelinated) = MyelinSheath(BareAxon) — fast pain reflex (~30 m/s).
C-fiber (unmyelinated) = BareAxon — slow burning pain (~1 m/s).

File này triển khai 9 phần:
    A. ANTI-PATTERN — inheritance explosion
    B. Component interface AxonSignal + ConcreteComponent BareAxon
    C. Abstract Decorator AxonDecorator
    D. 4 ConcreteDecorator sinh học
    E. Demo stacking biological decorators
    F. Demo MS (demyelination)
    G. Demo thứ tự stack matters
    H. Ellumm: StorageBackend với 5-decorator chain
    I. Python @decorator syntax — phụ lục so sánh
"""

from __future__ import annotations
import functools
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# =============================================================================
# A. ANTI-PATTERN — inheritance explosion
# =============================================================================
# 6 feature → 2^6 = 64 subclass nếu inheritance. Diamond problem nặng.

# Chỉ minh họa, KHÔNG làm theo:
# class FastLoggingCachingValidatingProfilingAuthAxon(...): ...
#
# Decorator giải quyết: 6 feature → 6 class, stack runtime.


# =============================================================================
# B. Component + ConcreteComponent
# =============================================================================

@dataclass
class TransmissionResult:
    """Kết quả của transmit — signal + metadata về cách dẫn truyền."""
    signal_value: float
    latency_ms: float
    energy_cost: float
    log_trail: list[str] = field(default_factory=list)
    cached: bool = False


class AxonSignal(ABC):
    """Component interface — mọi decorator và component cốt lõi đều implement."""
    @abstractmethod
    def transmit(self, signal_value: float) -> TransmissionResult: ...


class BareAxon(AxonSignal):
    """ConcreteComponent — axon trần, không myelin. Chậm và tốn năng lượng."""

    def __init__(self, length_mm: float = 100.0):
        self._length = length_mm
        self._base_speed_mps = 1.0    # 1 m/s = 1 mm/ms

    def transmit(self, signal_value: float) -> TransmissionResult:
        latency = self._length / self._base_speed_mps   # mm / (mm/ms) = ms
        energy = self._length * 0.10                    # cao: AP ở mọi điểm
        return TransmissionResult(
            signal_value=signal_value,
            latency_ms=latency,
            energy_cost=energy,
            log_trail=[f"BareAxon: {self._length}mm @ 1 m/s"],
        )


# =============================================================================
# C. Abstract Decorator
# =============================================================================

class AxonDecorator(AxonSignal, ABC):
    """Wraps một AxonSignal khác. Cũng IS-A AxonSignal."""

    def __init__(self, inner: AxonSignal):
        self._inner = inner

    @abstractmethod
    def transmit(self, signal_value: float) -> TransmissionResult: ...


# =============================================================================
# D. ConcreteDecorator — 4 decorator sinh học
# =============================================================================

class MyelinSheath(AxonDecorator):
    """
    Saltatory conduction: AP nhảy giữa Nodes of Ranvier.
    Tốc độ tăng x100, năng lượng giảm 70% (chỉ AP active ở node).
    """
    def __init__(self, inner: AxonSignal, speedup: float = 100.0,
                 energy_reduction: float = 0.7):
        super().__init__(inner)
        self._speedup = speedup
        self._energy_reduction = energy_reduction

    def transmit(self, signal_value: float) -> TransmissionResult:
        result = self._inner.transmit(signal_value)
        # Apply myelin effect: tăng tốc + giảm năng lượng
        result.latency_ms /= self._speedup
        result.energy_cost *= (1.0 - self._energy_reduction)
        result.log_trail.append(f"MyelinSheath: speedup x{self._speedup}, "
                                f"energy -{self._energy_reduction*100:.0f}%")
        return result


class PerineuronalNet(AxonDecorator):
    """
    Perineuronal nets bao quanh cell body và dendrite (không phải axon strict,
    nhưng cùng tinh thần Decorator). Stabilize synapse, hạn chế new plasticity.
    Trong code mô phỏng: thêm 'lock' trên signal — không cho phép rewrite.
    """
    def __init__(self, inner: AxonSignal):
        super().__init__(inner)

    def transmit(self, signal_value: float) -> TransmissionResult:
        result = self._inner.transmit(signal_value)
        # PNN lock: signal_value bị "ổn định hóa" — quantize 1 chữ số
        result.signal_value = round(result.signal_value, 1)
        result.log_trail.append("PerineuronalNet: signal locked (quantized .1)")
        return result


class GlialEnsheathment(AxonDecorator):
    """
    Astrocyte process bao quanh synapse (tripartite synapse).
    K+ buffering, glutamate uptake → tăng signal-to-noise ratio.
    Trong code mô phỏng: tăng signal_value 10% (giảm noise).
    """
    def __init__(self, inner: AxonSignal, snr_boost: float = 0.1):
        super().__init__(inner)
        self._boost = snr_boost

    def transmit(self, signal_value: float) -> TransmissionResult:
        result = self._inner.transmit(signal_value)
        result.signal_value *= (1.0 + self._boost)
        result.log_trail.append(f"GlialEnsheathment: SNR boost +{self._boost*100:.0f}%")
        return result


class NodalTightening(AxonDecorator):
    """
    Paranodal junction tightening — myelin compaction tinh tế.
    Tăng thêm conductive efficiency.
    """
    def transmit(self, signal_value: float) -> TransmissionResult:
        result = self._inner.transmit(signal_value)
        result.latency_ms *= 0.85    # giảm thêm 15% latency
        result.log_trail.append("NodalTightening: paranodal junction sealed (-15% latency)")
        return result


# =============================================================================
# Cross-cutting decorator (kỹ thuật, không sinh học)
# =============================================================================

class LoggingDecorator(AxonDecorator):
    def __init__(self, inner: AxonSignal, label: str = "log"):
        super().__init__(inner)
        self._label = label

    def transmit(self, signal_value: float) -> TransmissionResult:
        print(f"  [{self._label}] BEFORE transmit: signal={signal_value}")
        result = self._inner.transmit(signal_value)
        print(f"  [{self._label}] AFTER transmit: signal={result.signal_value:.3f}, "
              f"latency={result.latency_ms:.2f}ms, energy={result.energy_cost:.2f}, "
              f"cached={result.cached}")
        result.log_trail.append(f"LoggingDecorator [{self._label}]")
        return result


class CachingDecorator(AxonDecorator):
    def __init__(self, inner: AxonSignal):
        super().__init__(inner)
        self._cache: dict[float, TransmissionResult] = {}

    def transmit(self, signal_value: float) -> TransmissionResult:
        if signal_value in self._cache:
            cached_result = self._cache[signal_value]
            # Trả về copy với cached=True để biết là cache hit
            return TransmissionResult(
                signal_value=cached_result.signal_value,
                latency_ms=0.001,                 # cache hit gần như instant
                energy_cost=0.001,
                log_trail=cached_result.log_trail + ["CachingDecorator: HIT"],
                cached=True,
            )
        result = self._inner.transmit(signal_value)
        self._cache[signal_value] = result
        result.log_trail.append("CachingDecorator: MISS, cached")
        return result


# =============================================================================
# H. ELLUMM — StorageBackend với chain decorator
# =============================================================================

class StorageBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[Any]: ...
    @abstractmethod
    def put(self, key: str, value: Any) -> None: ...


class SQLiteStorage(StorageBackend):
    """Concrete component — backend cốt lõi."""
    def __init__(self):
        self._table: dict[str, Any] = {}
        self.calls = {"get": 0, "put": 0}

    def get(self, key):
        self.calls["get"] += 1
        time.sleep(0.001)        # mô phỏng disk I/O
        return self._table.get(key)

    def put(self, key, value):
        self.calls["put"] += 1
        time.sleep(0.001)
        self._table[key] = value


class StorageDecorator(StorageBackend, ABC):
    def __init__(self, inner: StorageBackend):
        self._inner = inner


class LogStorageDecorator(StorageDecorator):
    def get(self, key):
        print(f"    [LOG] get('{key}')")
        return self._inner.get(key)
    def put(self, key, value):
        print(f"    [LOG] put('{key}', ...)")
        self._inner.put(key, value)


class CacheStorageDecorator(StorageDecorator):
    def __init__(self, inner: StorageBackend):
        super().__init__(inner)
        self._cache: dict[str, Any] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key):
        if key in self._cache:
            self.hits += 1
            return self._cache[key]
        self.misses += 1
        value = self._inner.get(key)
        if value is not None:
            self._cache[key] = value
        return value

    def put(self, key, value):
        self._cache[key] = value
        self._inner.put(key, value)


class ProfilingStorageDecorator(StorageDecorator):
    def __init__(self, inner: StorageBackend):
        super().__init__(inner)
        self.timings: list[float] = []

    def get(self, key):
        start = time.perf_counter()
        result = self._inner.get(key)
        self.timings.append(time.perf_counter() - start)
        return result

    def put(self, key, value):
        start = time.perf_counter()
        self._inner.put(key, value)
        self.timings.append(time.perf_counter() - start)


class AuthStorageDecorator(StorageDecorator):
    """Note: GoF Decorator có thể overlap với Proxy ở semantic auth.
    Tách ranh giới: nếu chính function 'auth check + delegate' thì là Decorator,
    nếu thay đổi cách truy cập object (lazy/remote/access control) → Proxy."""
    def __init__(self, inner: StorageBackend, allowed_keys: set[str]):
        super().__init__(inner)
        self._allowed = allowed_keys

    def get(self, key):
        if key not in self._allowed:
            raise PermissionError(f"Not authorized to read '{key}'")
        return self._inner.get(key)

    def put(self, key, value):
        if key not in self._allowed:
            raise PermissionError(f"Not authorized to write '{key}'")
        self._inner.put(key, value)


# =============================================================================
# I. Python @decorator syntax — phụ lục
# =============================================================================
# Python có cú pháp @decorator cho function, là biến thể đơn giản của pattern.
# Stack `@cached @logged` tương đương `cached(logged(func))`.

def py_logged(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print(f"    [py_logged] calling {func.__name__}({args}, {kwargs})")
        result = func(*args, **kwargs)
        print(f"    [py_logged] returned {result}")
        return result
    return wrapper


def py_cached(func: Callable) -> Callable:
    cache: dict = {}
    @functools.wraps(func)
    def wrapper(*args):
        if args in cache:
            print(f"    [py_cached] HIT for {args}")
            return cache[args]
        result = func(*args)
        cache[args] = result
        return result
    return wrapper


@py_cached
@py_logged
def compute_signal_strength(intensity: float, distance: float) -> float:
    """Function với 2 decorator chồng. Tương đương:
       compute_signal_strength = py_cached(py_logged(compute_signal_strength))"""
    return intensity / (1.0 + distance ** 2)


# =============================================================================
# DEMO
# =============================================================================

def demo() -> None:
    print("=" * 64)
    print("E. STACKING BIOLOGICAL DECORATORS")
    print("=" * 64)

    # Bare axon (C-fiber)
    bare = BareAxon(length_mm=500.0)
    r0 = bare.transmit(signal_value=0.95)
    print(f"  BareAxon (C-fiber):")
    print(f"    latency={r0.latency_ms:.1f}ms, energy={r0.energy_cost:.2f}")

    # Add myelin (Aδ-fiber)
    aδ = MyelinSheath(BareAxon(length_mm=500.0))
    r1 = aδ.transmit(signal_value=0.95)
    print(f"\n  MyelinSheath(BareAxon) (Aδ-fiber):")
    print(f"    latency={r1.latency_ms:.2f}ms ({r0.latency_ms / r1.latency_ms:.0f}x faster), "
          f"energy={r1.energy_cost:.2f}")

    # Add nodal tightening
    fast = NodalTightening(MyelinSheath(BareAxon(length_mm=500.0)))
    r2 = fast.transmit(signal_value=0.95)
    print(f"\n  NodalTightening(MyelinSheath(BareAxon)):")
    print(f"    latency={r2.latency_ms:.2f}ms, energy={r2.energy_cost:.2f}")

    # Stack thêm glia + PNN
    full = PerineuronalNet(GlialEnsheathment(NodalTightening(MyelinSheath(BareAxon(length_mm=500.0)))))
    r3 = full.transmit(signal_value=0.95)
    print(f"\n  PNN(Glia(NodalTight(Myelin(BareAxon)))) — full neuron:")
    print(f"    signal={r3.signal_value} (boosted+locked), latency={r3.latency_ms:.2f}ms")
    print(f"    Log trail:")
    for entry in r3.log_trail:
        print(f"      • {entry}")

    print()
    print("=" * 64)
    print("F. MS — DEMYELINATION (remove MyelinSheath decorator)")
    print("=" * 64)
    healthy = MyelinSheath(BareAxon(length_mm=500.0))
    sick = BareAxon(length_mm=500.0)        # myelin attacked away

    r_h = healthy.transmit(0.95)
    r_s = sick.transmit(0.95)
    print(f"  Healthy (myelinated): latency={r_h.latency_ms:.2f}ms")
    print(f"  MS patient (demyelinated): latency={r_s.latency_ms:.2f}ms")
    print(f"  → Slowdown: {r_s.latency_ms / r_h.latency_ms:.0f}x (matches clinical 10-20x)")
    print(f"  Bệnh nhân: motor weakness, optic neuritis, ataxia, fatigue.")

    print()
    print("=" * 64)
    print("G. ORDER MATTERS — Cache trong vs ngoài Logging")
    print("=" * 64)

    print("\n  Order A: LoggingDecorator(CachingDecorator(BareAxon))")
    print("    → Logging ở NGOÀI → log THẤY cả cache hit (cached=True ở dòng AFTER)")
    chain_a = LoggingDecorator(CachingDecorator(BareAxon(50.0)), label="LOG-A")
    chain_a.transmit(0.5)
    chain_a.transmit(0.5)   # cache hit — log vẫn chạy ngoài cùng

    print("\n  Order B: CachingDecorator(LoggingDecorator(BareAxon))")
    print("    → Logging ở TRONG cache → cache hit BYPASS log → log không chạy lần 2")
    chain_b = CachingDecorator(LoggingDecorator(BareAxon(50.0), label="LOG-B"))
    print("    First call (miss):")
    chain_b.transmit(0.7)
    print("    Second call (cache hit, log không chạy):")
    r_hit = chain_b.transmit(0.7)
    print(f"    Result.cached = {r_hit.cached}")

    print()
    print("=" * 64)
    print("H. ELLUMM — StorageBackend với 4-decorator chain")
    print("=" * 64)

    # Build chain: Auth → Cache → Profiling → Logging → SQLite
    sqlite = SQLiteStorage()
    profiler = ProfilingStorageDecorator(sqlite)
    cached_storage = CacheStorageDecorator(profiler)
    storage = LogStorageDecorator(cached_storage)
    storage = AuthStorageDecorator(storage, allowed_keys={"ep_001", "ep_002"})

    # Test 1: ghi 2 episode
    print("\n  Ghi 2 episode:")
    storage.put("ep_001", {"content": "saw apple", "salience": 0.6})
    storage.put("ep_002", {"content": "heard bell", "salience": 0.85})

    # Test 2: đọc — first time MISS
    print("\n  Đọc ep_001 (cache miss):")
    storage.get("ep_001")

    # Test 3: đọc lại — HIT
    print("\n  Đọc ep_001 lần 2 (cache hit):")
    r = storage.get("ep_001")
    print(f"    cache hits: {cached_storage.hits}, misses: {cached_storage.misses}")

    # Test 4: auth fail
    print("\n  Đọc ep_999 (không trong allowed_keys):")
    try:
        storage.get("ep_999")
    except PermissionError as e:
        print(f"    ✓ Auth blocked: {e}")

    print(f"\n  SQLite calls: {sqlite.calls}")
    print(f"  Profiler timings: {[f'{t*1000:.2f}ms' for t in profiler.timings[:5]]}")

    print()
    print("=" * 64)
    print("I. Python @decorator SYNTAX — function-level Decorator")
    print("=" * 64)
    print("\n  compute_signal_strength(0.8, 2.0):")
    r1 = compute_signal_strength(0.8, 2.0)
    print(f"    result = {r1:.4f}")

    print("\n  compute_signal_strength(0.8, 2.0) lần 2 (cache hit):")
    r2 = compute_signal_strength(0.8, 2.0)
    print(f"    result = {r2:.4f}")

    print("\n  compute_signal_strength(0.5, 5.0) (mới — miss):")
    r3 = compute_signal_strength(0.5, 5.0)
    print(f"    result = {r3:.4f}")
    print("\n  → @py_cached @py_logged tương đương py_cached(py_logged(func))")
    print("    Cú pháp Python ngắn gọn hơn class-based GoF Decorator,")
    print("    nhưng cùng tinh thần wrap-to-add-behavior.")


if __name__ == "__main__":
    demo()


# =============================================================================
# THẢO LUẬN
# =============================================================================
#
# DECORATOR vs PROXY (lesson 12)
# ───────────────────────────────
# Cả hai đều wrap object cùng interface. Khác biệt INTENT:
# - Decorator: thêm hành vi tự nhiên (logging, caching, validation)
# - Proxy: kiểm soát truy cập (auth, lazy load, remote, copy-on-write)
#
# Auth decorator vs auth proxy là edge case. Quy tắc: nếu chỉ check + delegate
# và không kiểm soát lifecycle/identity của object → Decorator.
#
# DECORATOR vs CHAIN OF RESPONSIBILITY (lesson 13)
# ─────────────────────────────────────────────────
# Cả hai đều "stack" handler. Khác biệt:
# - Decorator: mỗi handler luôn delegate, kết quả lan ngược ra
# - Chain of Responsibility: handler có thể "stop" chain, không pass tiếp
#
# Decorator dùng cho ENRICHMENT (mỗi tầng thêm cái gì đó).
# CoR dùng cho ESCALATION (tầng nào xử lý được thì xử lý).
#
# WHEN NOT TO DECORATE
# ────────────────────
# - Decorator state phức tạp + side effect → khó debug.
# - Chain quá sâu (>5 decorator) → stack trace không đọc nổi.
# - Decorator với thứ tự semantic không rõ → bug ngầm.
# - Mỗi decorator chỉ wrap 1 method nhỏ → over-engineering, dùng @decorator syntax.
#
# Architect rule: nếu bạn không thể nói tên thứ tự decorator của mình mà không
# nhìn code, chain đã quá phức tạp → tách thành named pipeline rõ ràng.
"""
"""
