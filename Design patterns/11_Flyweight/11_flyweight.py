# -*- coding: utf-8 -*-
"""
Lesson 11 — Flyweight Pattern
Analogy: Receptor type (GABA-A, AMPA, NMDA) chia sẻ thiết kế giữa hàng tỷ synapse.

Cấu trúc file:
  Section 1: Anti-pattern — mỗi synapse ôm full receptor design (memory blow up)
  Section 2: Flyweight đúng — ReceptorType (intrinsic, immutable) + Synapse (extrinsic)
  Section 3: ReceptorFactory — cache + identity guarantee
  Section 4: Demo memory savings + identity check
  Section 5: Failure case — mutable flyweight gây disaster
  Section 6: Extension — thêm NMDA receptor (Open-Closed)
  Section 7: Ellumm — ConceptFlyweight cho memory episode
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import sys


# ============================================================
# SECTION 1: ANTI-PATTERN — mỗi synapse ôm full design
# ============================================================
class FatSynapse:
    """❌ Mỗi instance copy toàn bộ receptor design."""
    def __init__(self, location: str):
        # Toàn bộ block sau là DUPLICATE giữa các synapse cùng type
        self.subunits = ['α1', 'α1', 'β2', 'β2', 'γ2']
        self.kinetics = {'open_rate': 1e3, 'close_rate': 1e2, 'desensitize': 50}
        self.pharmacology = {'GABA_Kd': 5e-6, 'benzodiazepine_site': True}
        self.ion_selectivity = {'Cl-': 1.0}
        # Phần đặc thù (extrinsic) — đáng lẽ chỉ phần này
        self.location = location
        self.voltage = -70.0
        self.ligand_conc = 0.0


# ============================================================
# SECTION 2: FLYWEIGHT đúng — IMMUTABLE intrinsic
# ============================================================
@dataclass(frozen=True, slots=True)
class ReceptorType:
    """FLYWEIGHT — chứa intrinsic state, IMMUTABLE.

    `frozen=True`: không cho set lại sau __init__ → safety guarantee.
    `slots=True`: layout chặt, giảm memory ~40-50%.
    """
    name: str
    subunits: Tuple[str, ...]                  # tuple thay list (immutable)
    kinetics: Tuple[Tuple[str, float], ...]    # frozen dict-like
    pharmacology: Tuple[Tuple[str, object], ...]
    ion_selectivity: Tuple[Tuple[str, float], ...]

    def gate(self, ligand_conc: float, voltage: float) -> float:
        """OPERATION dùng intrinsic + extrinsic, trả về current."""
        kin = dict(self.kinetics)
        # Đơn giản hóa: current ~ open_rate × [ligand] × driving force
        if ligand_conc <= 0:
            return 0.0
        rev_potential = -75.0 if 'GABA' in self.name else 0.0  # Cl- vs cation
        driving = voltage - rev_potential
        open_prob = ligand_conc / (ligand_conc + 5e-6)  # Hill-like
        return kin['open_rate'] * open_prob * driving * 1e-6


# ============================================================
# SECTION 3: FLYWEIGHT FACTORY — cache + identity
# ============================================================
class ReceptorFactory:
    """Đảm bảo: cùng type_name → cùng instance (identity-equal)."""
    _cache: Dict[str, ReceptorType] = {}
    _build_count: int = 0

    @classmethod
    def get(cls, type_name: str) -> ReceptorType:
        if type_name not in cls._cache:
            cls._cache[type_name] = cls._build(type_name)
            cls._build_count += 1
        return cls._cache[type_name]

    @classmethod
    def _build(cls, type_name: str) -> ReceptorType:
        catalog = {
            'GABA_A': ReceptorType(
                name='GABA_A',
                subunits=('α1', 'α1', 'β2', 'β2', 'γ2'),
                kinetics=(('open_rate', 1e3), ('close_rate', 1e2), ('desensitize', 50)),
                pharmacology=(('GABA_Kd', 5e-6), ('benzodiazepine_site', True)),
                ion_selectivity=(('Cl-', 1.0),),
            ),
            'AMPA': ReceptorType(
                name='AMPA',
                subunits=('GluA1', 'GluA2', 'GluA2', 'GluA3'),
                kinetics=(('open_rate', 5e3), ('close_rate', 8e2), ('desensitize', 200)),
                pharmacology=(('glutamate_Kd', 1e-5), ('Ca_permeable_if_no_GluA2', True)),
                ion_selectivity=(('Na+', 1.0), ('K+', 1.0)),
            ),
            'NMDA': ReceptorType(  # thêm sau, chứng minh Open-Closed
                name='NMDA',
                subunits=('GluN1', 'GluN1', 'GluN2A', 'GluN2A'),
                kinetics=(('open_rate', 80), ('close_rate', 30), ('Mg_block', True)),
                pharmacology=(('glutamate_Kd', 1e-6), ('glycine_required', True), ('voltage_dependent', True)),
                ion_selectivity=(('Na+', 1.0), ('K+', 1.0), ('Ca2+', 10.0)),
            ),
        }
        if type_name not in catalog:
            raise ValueError(f"Unknown receptor type: {type_name}")
        return catalog[type_name]

    @classmethod
    def stats(cls) -> Dict[str, int]:
        return {'cached_types': len(cls._cache), 'build_calls': cls._build_count}

    @classmethod
    def reset(cls):
        cls._cache.clear()
        cls._build_count = 0


# ============================================================
# CONTEXT — Synapse chứa extrinsic state, reference đến Flyweight
# ============================================================
class Synapse:
    """Mỗi synapse chỉ giữ extrinsic state + pointer đến ReceptorType."""
    __slots__ = ('receptor_type', 'location', 'voltage', 'ligand_conc')

    def __init__(self, receptor_type_name: str, location: str):
        self.receptor_type: ReceptorType = ReceptorFactory.get(receptor_type_name)
        self.location: str = location
        self.voltage: float = -70.0
        self.ligand_conc: float = 0.0

    def fire(self) -> float:
        return self.receptor_type.gate(self.ligand_conc, self.voltage)


# ============================================================
# SECTION 4: DEMO — memory + identity
# ============================================================
def demo_memory_savings(N: int = 10_000):
    print("=" * 64)
    print(f"DEMO 1 — Memory savings với N={N:,} synapse")
    print("=" * 64)

    # Anti-pattern
    fat = [FatSynapse(f"loc_{i}") for i in range(N)]
    fat_size = sys.getsizeof(fat) + sum(
        sys.getsizeof(s.subunits) + sys.getsizeof(s.kinetics) +
        sys.getsizeof(s.pharmacology) + sys.getsizeof(s.ion_selectivity)
        for s in fat
    )

    # Flyweight
    ReceptorFactory.reset()
    fly = [Synapse('GABA_A', f"loc_{i}") for i in range(N)]
    fly_size = sys.getsizeof(fly) + N * 8 * 4  # 4 slots, mỗi slot ~8 bytes
    type_size = sys.getsizeof(ReceptorFactory.get('GABA_A'))

    print(f"  Anti-pattern (FatSynapse): ~{fat_size:,} bytes")
    print(f"  Flyweight   (Synapse):     ~{fly_size + type_size:,} bytes")
    print(f"  Tiết kiệm: {(1 - (fly_size + type_size) / fat_size) * 100:.1f}%")
    print(f"  Factory stats: {ReceptorFactory.stats()}")


def demo_identity():
    print()
    print("=" * 64)
    print("DEMO 2 — Identity guarantee (a is b)")
    print("=" * 64)
    ReceptorFactory.reset()
    s1 = Synapse('GABA_A', 'dendrite_3')
    s2 = Synapse('GABA_A', 'soma')
    s3 = Synapse('AMPA', 'dendrite_5')

    print(f"  s1.receptor IS s2.receptor (cùng GABA_A)? {s1.receptor_type is s2.receptor_type}")
    print(f"  s1.receptor IS s3.receptor (khác type)?    {s1.receptor_type is s3.receptor_type}")
    print(f"  Factory chỉ build {ReceptorFactory.stats()['build_calls']} type cho 3 synapse")


# ============================================================
# SECTION 5: FAILURE CASE — mutable flyweight = disaster
# ============================================================
def demo_failure_mutable():
    print()
    print("=" * 64)
    print("DEMO 3 — Failure: mutable flyweight (cảnh báo)")
    print("=" * 64)

    @dataclass  # CỐ Ý không frozen → demo hậu quả
    class MutableReceptor:
        name: str
        conductance: float

    class BadFactory:
        _cache: Dict[str, MutableReceptor] = {}
        @classmethod
        def get(cls, name):
            if name not in cls._cache:
                cls._cache[name] = MutableReceptor(name, conductance=1.0)
            return cls._cache[name]

    # 1 triệu synapse share cùng instance
    syn_a = BadFactory.get('GABA_A')
    syn_b = BadFactory.get('GABA_A')
    assert syn_a is syn_b
    print(f"  Trước: syn_a.conductance={syn_a.conductance}, syn_b.conductance={syn_b.conductance}")

    # Một thread "modulate" syn_a (e.g., do thuốc local)
    syn_a.conductance = 999
    print(f"  Sau syn_a.conductance=999:")
    print(f"    syn_a.conductance = {syn_a.conductance}")
    print(f"    syn_b.conductance = {syn_b.conductance}  ← BỊ THAY ĐỔI THEO!")
    print(f"  → Tất cả synapse GABA-A trong não vừa bị set conductance=999.")
    print(f"  → Bài học: Flyweight PHẢI immutable (frozen dataclass / __slots__ + property).")


# ============================================================
# SECTION 6: EXTENSION — thêm NMDA (chứng minh Open-Closed)
# ============================================================
def demo_extension():
    print()
    print("=" * 64)
    print("DEMO 4 — Extension: thêm NMDA receptor mới (Open-Closed)")
    print("=" * 64)
    ReceptorFactory.reset()
    nmda_syn = Synapse('NMDA', 'dendrite_spine_7')
    nmda_syn.ligand_conc = 1e-5
    nmda_syn.voltage = -40
    current = nmda_syn.fire()
    print(f"  NMDA synapse fired: current ~ {current:.6f}")
    print(f"  ⇒ Synapse class KHÔNG thay đổi, chỉ ReceptorFactory._build có catalog mới.")


# ============================================================
# SECTION 7: ELLUMM — ConceptFlyweight
# ============================================================
@dataclass(frozen=True, slots=True)
class ConceptToken:
    """FLYWEIGHT cho semantic concept trong Ellumm memory.
    Intrinsic: name, embedding (giả lập 8-dim), semantic_type.
    """
    name: str
    embedding: Tuple[float, ...]
    semantic_type: str  # 'object' / 'emotion' / 'action' / 'attribute'


class ConceptFactory:
    _cache: Dict[str, ConceptToken] = {}

    @classmethod
    def get(cls, name: str, semantic_type: str = 'object') -> ConceptToken:
        if name not in cls._cache:
            # Giả lập embedding bằng hash
            h = hash(name) & 0xFF
            emb = tuple((h >> i & 1) / 1.0 for i in range(8))
            cls._cache[name] = ConceptToken(name, emb, semantic_type)
        return cls._cache[name]

    @classmethod
    def stats(cls):
        return {'unique_concepts': len(cls._cache)}


@dataclass
class MemoryEpisode:
    episode_id: str
    concept_refs: List[Tuple[ConceptToken, int]] = field(default_factory=list)
    # extrinsic: position trong episode

    def add_concept(self, name: str, position: int, semantic_type: str = 'object'):
        token = ConceptFactory.get(name, semantic_type)
        self.concept_refs.append((token, position))

    def list_concepts(self) -> List[str]:
        return [t.name for t, _ in self.concept_refs]


def demo_ellumm():
    print()
    print("=" * 64)
    print("DEMO 5 — Ellumm: ConceptFlyweight cho 1000 episode")
    print("=" * 64)
    ConceptFactory._cache.clear()

    common_concepts = [('dog', 'object'), ('happy', 'emotion'), ('run', 'action'),
                       ('red', 'attribute'), ('park', 'object'), ('sad', 'emotion')]
    episodes: List[MemoryEpisode] = []
    for i in range(1000):
        ep = MemoryEpisode(episode_id=f"ep_{i:04d}")
        # Mỗi episode dùng vài concept random (mô phỏng)
        for j, (name, stype) in enumerate(common_concepts[:3 + i % 4]):
            ep.add_concept(name, position=j, semantic_type=stype)
        episodes.append(ep)

    print(f"  1000 episode được tạo, mỗi episode có 3-6 concept.")
    print(f"  Total concept references: {sum(len(e.concept_refs) for e in episodes):,}")
    print(f"  Unique ConceptToken instances: {ConceptFactory.stats()['unique_concepts']}")
    print(f"  ⇒ Tỷ lệ share = {sum(len(e.concept_refs) for e in episodes) / ConceptFactory.stats()['unique_concepts']:.1f}x")

    sample = episodes[42]
    print(f"\n  Sample episode {sample.episode_id}: {sample.list_concepts()}")


# ============================================================
# MAIN
# ============================================================
if __name__ == '__main__':
    demo_memory_savings(N=10_000)
    demo_identity()
    demo_failure_mutable()
    demo_extension()
    demo_ellumm()
    print()
    print("=" * 64)
    print("Lesson 11 — Flyweight: COMPLETE")
    print("=" * 64)
