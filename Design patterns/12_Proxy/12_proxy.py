# -*- coding: utf-8 -*-
"""
Lesson 12 — Proxy Pattern
Analogy: Blood-Brain Barrier (BBB) — proxy giữa máu và neuron.

Cấu trúc file:
  Section 1: Anti-pattern — Neuron tự lo mọi kiểm soát
  Section 2: Subject interface (IBrainSubstrate)
  Section 3: RealSubject (Vasculature)
  Section 4: BBBProxy — Protection + Filtering
  Section 5: Stacked Proxy (BBB → Astrocyte → Neuron)
  Section 6: Failure case — BBB breakdown (MS / stroke)
  Section 7: Demo bypass vulnerability
  Section 8: Ellumm — MemoryStore với Auth/Cache/RateLimit/LazyLoad proxy stack
"""

from __future__ import annotations
from typing import Protocol, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from abc import abstractmethod
import time


# ============================================================
# SECTION 1: ANTI-PATTERN
# ============================================================
class NaiveNeuron:
    """❌ Neuron tự kiểm tra độc, antibody — vi phạm SRP."""
    def consume_glucose(self, blood: dict):
        if blood.get('toxin'):
            blood = {k: v for k, v in blood.items() if k != 'toxin'}
        if blood.get('antibody'):
            return None  # tự reject
        return blood.get('glucose', 0)


# ============================================================
# SECTION 2: SUBJECT INTERFACE
# ============================================================
class IBrainSubstrate(Protocol):
    def request_glucose(self, demand: float) -> float: ...
    def request_oxygen(self, demand: float) -> float: ...
    def request_drug(self, name: str) -> Optional[str]: ...


# ============================================================
# SECTION 3: REAL SUBJECT — Vasculature
# ============================================================
class Vasculature:
    """Real subject: vasculature thật, có cả glucose tốt lẫn độc tố."""
    def __init__(self):
        self.blood_glucose: float = 5.5  # mM
        self.blood_oxygen: float = 0.95  # saturation
        self.contaminants: List[str] = ['toxin_X', 'antibody_IgG', 'bacterium']
        self.drug_pool: Dict[str, str] = {
            'morphine': 'lipid_soluble',
            'penicillin': 'water_soluble_no_transporter',
            'L-DOPA': 'has_LAT1_transporter',
            'insulin': 'large_protein',
        }
        self._delivery_log: List[str] = []

    def request_glucose(self, demand: float) -> float:
        delivered = min(demand, self.blood_glucose)
        self._delivery_log.append(f"glucose:{delivered:.2f}")
        return delivered

    def request_oxygen(self, demand: float) -> float:
        delivered = min(demand, self.blood_oxygen)
        self._delivery_log.append(f"oxygen:{delivered:.2f}")
        return delivered

    def request_drug(self, name: str) -> Optional[str]:
        # Naive: trả về raw kèm contaminants nếu có
        if name in self.drug_pool:
            return self.drug_pool[name]
        return None


# ============================================================
# SECTION 4: BBB PROXY — Protection + Filtering + Lazy
# ============================================================
class BBBProxy:
    """Proxy đứng giữa client (neuron) và Vasculature.

    - Lọc contaminants (Protection)
    - Chặn molecule không có transporter (Selective)
    - Lazy: không deliver nếu astrocyte không signal demand
    - Log cross-cutting
    """
    def __init__(self, real: Vasculature, astrocyte_demand: Callable[[], bool]):
        self.real = real
        self.astrocyte_demand = astrocyte_demand
        self.permeability: float = 1.0  # 1.0 = healthy, 0 = blocked
        self.access_log: List[str] = []
        self._allowed_drug_properties = {'lipid_soluble', 'has_LAT1_transporter'}

    def request_glucose(self, demand: float) -> float:
        if not self.astrocyte_demand():
            self.access_log.append(f"glucose: DENIED (no astrocyte signal)")
            return 0.0
        raw = self.real.request_glucose(demand)
        delivered = raw * self.permeability
        self.access_log.append(f"glucose: {raw:.2f} → {delivered:.2f} (perm={self.permeability})")
        return delivered

    def request_oxygen(self, demand: float) -> float:
        # Oxygen luôn pass — lipid soluble, không cần astrocyte signal
        delivered = self.real.request_oxygen(demand) * self.permeability
        self.access_log.append(f"oxygen: {delivered:.2f}")
        return delivered

    def request_drug(self, name: str) -> Optional[str]:
        prop = self.real.request_drug(name)
        if prop is None:
            self.access_log.append(f"drug:{name}: NOT IN POOL")
            return None
        if prop in self._allowed_drug_properties:
            self.access_log.append(f"drug:{name}: PASSED ({prop})")
            return prop
        else:
            self.access_log.append(f"drug:{name}: BLOCKED ({prop})")
            return None


# ============================================================
# SECTION 5: STACKED PROXY — BBB + Astrocyte + Neuron client
# ============================================================
class Neuron:
    """Client. Chỉ biết IBrainSubstrate, không biết về BBB hay Vasculature."""
    def __init__(self, substrate: IBrainSubstrate, name: str = "neuron"):
        self.substrate = substrate
        self.name = name
        self.atp: float = 0.0

    def metabolize(self, glucose_demand: float = 5.0):
        glu = self.substrate.request_glucose(glucose_demand)
        o2 = self.substrate.request_oxygen(0.5)
        # 1 glucose × 6 O2 → 36 ATP (đơn giản hóa)
        self.atp += min(glu, o2 / 0.1) * 36
        return self.atp


class AstrocyteSignal:
    """Phát signal demand_high khi neuron đang active."""
    def __init__(self):
        self.active: bool = True
    def __call__(self) -> bool:
        return self.active


# ============================================================
# SECTION 6: FAILURE CASE — BBB breakdown
# ============================================================
def demo_bbb_breakdown():
    print("=" * 64)
    print("DEMO 1 — BBB hoạt động bình thường")
    print("=" * 64)
    vasc = Vasculature()
    astro = AstrocyteSignal()
    bbb = BBBProxy(vasc, astrocyte_demand=astro)
    neuron = Neuron(bbb, name="cortex_pyramidal_1")

    neuron.metabolize(glucose_demand=5.0)
    print(f"  Neuron ATP: {neuron.atp:.1f}")
    print(f"  Drug morphine: {bbb.request_drug('morphine')}")
    print(f"  Drug penicillin: {bbb.request_drug('penicillin')}")
    print(f"  Drug insulin: {bbb.request_drug('insulin')}")
    print(f"  Access log:")
    for entry in bbb.access_log:
        print(f"    - {entry}")

    print()
    print("=" * 64)
    print("DEMO 2 — BBB breakdown (MS / stroke): permeability tụt")
    print("=" * 64)
    bbb.permeability = 0.3  # 70% damage
    neuron.atp = 0
    neuron.metabolize(glucose_demand=5.0)
    print(f"  Permeability=0.3 → Neuron ATP chỉ còn: {neuron.atp:.1f}")
    print(f"  → Neuron starve. Trong não thật: cell death + viêm.")


# ============================================================
# SECTION 7: BYPASS VULNERABILITY
# ============================================================
def demo_bypass_vulnerability():
    print()
    print("=" * 64)
    print("DEMO 3 — Bypass vulnerability (đường truy cập trực tiếp)")
    print("=" * 64)
    vasc = Vasculature()
    astro = AstrocyteSignal()
    bbb = BBBProxy(vasc, astrocyte_demand=astro)

    # Đúng: qua proxy
    via_proxy = bbb.request_drug('insulin')
    print(f"  Qua BBB proxy: insulin → {via_proxy}  (bị chặn)")

    # ❌ Sai: gọi thẳng vasc (giả lập leak hoặc bug code)
    via_direct = vasc.request_drug('insulin')
    print(f"  Bypass trực tiếp: insulin → {via_direct}  (lọt qua!)")
    print(f"  → Trong não: rò vasculature → insulin vào não → hypoglycemia trong não.")
    print(f"  → Bài học: encapsulate Vasculature; chỉ expose qua Proxy.")


# ============================================================
# SECTION 8: ELLUMM — Stacked Proxy cho MemoryStore
# ============================================================
class IMemoryStore(Protocol):
    def write(self, user: str, key: str, data: dict) -> bool: ...
    def read(self, user: str, key: str) -> Optional[dict]: ...


class MemoryStore:  # Real subject
    def __init__(self):
        self.db: Dict[str, dict] = {}
        self.disk_reads: int = 0

    def write(self, user: str, key: str, data: dict) -> bool:
        self.db[f"{user}:{key}"] = data
        return True

    def read(self, user: str, key: str) -> Optional[dict]:
        self.disk_reads += 1
        return self.db.get(f"{user}:{key}")


class AuthProxy:
    def __init__(self, real: IMemoryStore, allowed_users: set):
        self.real = real
        self.allowed = allowed_users
        self.deny_count = 0

    def write(self, user, key, data):
        if user not in self.allowed:
            self.deny_count += 1
            return False
        return self.real.write(user, key, data)

    def read(self, user, key):
        if user not in self.allowed:
            self.deny_count += 1
            return None
        return self.real.read(user, key)


class CacheProxy:
    def __init__(self, real: IMemoryStore):
        self.real = real
        self.cache: Dict[str, dict] = {}
        self.hits = 0
        self.misses = 0

    def write(self, user, key, data):
        result = self.real.write(user, key, data)
        # Invalidate cache khi write
        self.cache.pop(f"{user}:{key}", None)
        return result

    def read(self, user, key):
        ck = f"{user}:{key}"
        if ck in self.cache:
            self.hits += 1
            return self.cache[ck]
        self.misses += 1
        result = self.real.read(user, key)
        if result is not None:
            self.cache[ck] = result
        return result


class RateLimitProxy:
    def __init__(self, real: IMemoryStore, max_per_sec: int = 5):
        self.real = real
        self.max = max_per_sec
        self.window: List[float] = []
        self.throttled = 0

    def _allow(self):
        now = time.time()
        self.window = [t for t in self.window if now - t < 1.0]
        if len(self.window) >= self.max:
            self.throttled += 1
            return False
        self.window.append(now)
        return True

    def write(self, user, key, data):
        if not self._allow():
            return False
        return self.real.write(user, key, data)

    def read(self, user, key):
        if not self._allow():
            return None
        return self.real.read(user, key)


def demo_ellumm():
    print()
    print("=" * 64)
    print("DEMO 4 — Ellumm: stacked proxy cho MemoryStore")
    print("=" * 64)
    real = MemoryStore()
    # Stack: client → RateLimit → Auth → Cache → Real
    cached = CacheProxy(real)
    authed = AuthProxy(cached, allowed_users={'nam_son', 'ellumm_agent'})
    limited = RateLimitProxy(authed, max_per_sec=10)

    # Ghi 3 episode
    limited.write('nam_son', 'ep_001', {'event': 'saw dog', 'salience': 0.7})
    limited.write('nam_son', 'ep_002', {'event': 'happy moment', 'salience': 0.5})
    limited.write('hacker', 'ep_999', {'event': 'inject'})  # auth fail

    # Đọc 5 lần ep_001 → 1 miss + 4 hit
    for _ in range(5):
        limited.read('nam_son', 'ep_001')

    # Đọc bằng user khác
    limited.read('hacker', 'ep_001')

    print(f"  RealStore disk_reads: {real.disk_reads}  (chỉ 1 do cache)")
    print(f"  CacheProxy hits/misses: {cached.hits}/{cached.misses}")
    print(f"  AuthProxy deny_count: {authed.deny_count}")
    print(f"  RateLimitProxy throttled: {limited.throttled}")
    print(f"  ⇒ Mỗi proxy 1 concern, client (Ellumm agent) chỉ biết IMemoryStore.")


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    demo_bbb_breakdown()
    demo_bypass_vulnerability()
    demo_ellumm()
    print()
    print("=" * 64)
    print("Lesson 12 — Proxy: COMPLETE")
    print("=" * 64)
