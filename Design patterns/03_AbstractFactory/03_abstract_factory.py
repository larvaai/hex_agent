"""
Lesson 03 — Abstract Factory Pattern
Ví dụ neuroscience: mỗi vùng não (cortex, cerebellum, hippocampus) cần
một HỌ tế bào và mô khớp nhau:
    principal neuron + supporting glia + ECM + vasculature

Bergmann glia chỉ có ở cerebellum. Protoplasmic astrocyte chỉ ở cortex.
Trộn họ = heterotopia = bệnh thần kinh.

File này triển khai 5 phần:
    A. 4 abstract product interfaces
    B. 3 concrete families: Cortical / Cerebellar / Hippocampal
    C. Family integrity check tại runtime (compatible_with)
    D. Demo failure: ép trộn họ → ngoại lệ
    E. Ellumm version: ModalityEcosystem cho visual/auditory/interoceptive
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass


# =============================================================================
# A. ABSTRACT PRODUCT INTERFACES
# =============================================================================

class PrincipalNeuron(ABC):
    region: str
    @abstractmethod
    def fire(self) -> str: ...

class SupportingGlia(ABC):
    region: str
    @abstractmethod
    def support(self, neuron: PrincipalNeuron) -> str: ...

class ExtracellularMatrix(ABC):
    region: str
    @abstractmethod
    def composition(self) -> str: ...

class Vasculature(ABC):
    region: str
    @abstractmethod
    def bbb_tightness(self) -> str: ...


# =============================================================================
# B1. CORTICAL FAMILY
# =============================================================================

class PyramidalNeuron(PrincipalNeuron):
    region = "cortex"
    def fire(self) -> str:
        return "pyramidal burst → glutamate release into apical dendrite tuft"

class ProtoplasmicAstrocyte(SupportingGlia):
    region = "cortex"
    def support(self, neuron: PrincipalNeuron) -> str:
        if neuron.region != self.region:
            raise FamilyMismatch(self, neuron)
        return "glutamate-glutamine cycle, K+ buffering, tripartite synapse"

class CorticalECM(ExtracellularMatrix):
    region = "cortex"
    def composition(self) -> str:
        return "hyaluronan + tenascin-C + perineuronal nets quanh PV interneurons"

class CorticalBBB(Vasculature):
    region = "cortex"
    def bbb_tightness(self) -> str:
        return "tight (claudin-5 + occludin, đa số phân tử bị chặn)"


# =============================================================================
# B2. CEREBELLAR FAMILY
# =============================================================================

class PurkinjeCell(PrincipalNeuron):
    region = "cerebellum"
    def fire(self) -> str:
        return "complex spike (climbing fiber) hoặc simple spike (parallel fiber)"

class BergmannGlia(SupportingGlia):
    """
    Bergmann glia là kiểu radial glia chỉ tồn tại ở cerebellum.
    Bao quanh Purkinje cell, hỗ trợ migration của granule cell.
    Đặt Bergmann glia ở cortex là vô nghĩa — không có Purkinje để wrap.
    """
    region = "cerebellum"
    def support(self, neuron: PrincipalNeuron) -> str:
        if neuron.region != self.region:
            raise FamilyMismatch(self, neuron)
        return "wrap Purkinje dendrite, guide granule cell migration"

class CerebellarECM(ExtracellularMatrix):
    region = "cerebellum"
    def composition(self) -> str:
        return "cerebellar-specific proteoglycans, gắn parallel fibers chặt"

class CerebellarBBB(Vasculature):
    region = "cerebellum"
    def bbb_tightness(self) -> str:
        return "tight, mật độ cao do nhu cầu chuyển hóa của granule cells"


# =============================================================================
# B3. HIPPOCAMPAL FAMILY
# =============================================================================

class DentateGranuleCell(PrincipalNeuron):
    region = "hippocampus"
    def fire(self) -> str:
        return "sparse coding burst, mossy fiber output to CA3"

class HippocampalRadialGlia(SupportingGlia):
    """
    Khác với cortex/cerebellum, radial glia ở dentate gyrus VẪN là stem cell
    suốt đời (adult neurogenesis). Đây là điểm đặc biệt sinh học.
    """
    region = "hippocampus"
    def support(self, neuron: PrincipalNeuron) -> str:
        if neuron.region != self.region:
            raise FamilyMismatch(self, neuron)
        return "vẫn neurogenic ở người trưởng thành — sinh granule cell mới"

class HippocampalECM(ExtracellularMatrix):
    region = "hippocampus"
    def composition(self) -> str:
        return "perineuronal nets thưa hơn cortex → plasticity cao hơn"

class HippocampalBBB(Vasculature):
    region = "hippocampus"
    def bbb_tightness(self) -> str:
        return "tight nhưng leaky hơn cortex chút (allow corticosteroid)"


# =============================================================================
# EXCEPTIONS
# =============================================================================

class FamilyMismatch(Exception):
    def __init__(self, comp_a, comp_b):
        super().__init__(
            f"Family mismatch: {type(comp_a).__name__} (region={comp_a.region}) "
            f"không hỗ trợ {type(comp_b).__name__} (region={comp_b.region}). "
            f"Đây là 'heterotopia' trong code — sai họ ecosystem."
        )


# =============================================================================
# B. ABSTRACT FACTORY + CONCRETE FACTORIES
# =============================================================================

class BrainRegionEcosystem(ABC):
    @abstractmethod
    def create_principal_neuron(self) -> PrincipalNeuron: ...
    @abstractmethod
    def create_supporting_glia(self) -> SupportingGlia: ...
    @abstractmethod
    def create_ecm(self) -> ExtracellularMatrix: ...
    @abstractmethod
    def create_vasculature(self) -> Vasculature: ...


class CorticalEcosystem(BrainRegionEcosystem):
    def create_principal_neuron(self): return PyramidalNeuron()
    def create_supporting_glia(self):  return ProtoplasmicAstrocyte()
    def create_ecm(self):              return CorticalECM()
    def create_vasculature(self):      return CorticalBBB()

class CerebellarEcosystem(BrainRegionEcosystem):
    def create_principal_neuron(self): return PurkinjeCell()
    def create_supporting_glia(self):  return BergmannGlia()
    def create_ecm(self):              return CerebellarECM()
    def create_vasculature(self):      return CerebellarBBB()

class HippocampalEcosystem(BrainRegionEcosystem):
    def create_principal_neuron(self): return DentateGranuleCell()
    def create_supporting_glia(self):  return HippocampalRadialGlia()
    def create_ecm(self):              return HippocampalECM()
    def create_vasculature(self):      return HippocampalBBB()


# =============================================================================
# CLIENT — composition root build vùng não
# =============================================================================

@dataclass
class BrainRegion:
    name: str
    neuron: PrincipalNeuron
    glia: SupportingGlia
    ecm: ExtracellularMatrix
    vessel: Vasculature

    def operate(self) -> None:
        # Family integrity check — runtime guard
        print(f"\n  Region '{self.name}':")
        print(f"    Neuron: {self.neuron.fire()}")
        # Nếu glia sai họ, support() raise FamilyMismatch
        print(f"    Glia support: {self.glia.support(self.neuron)}")
        print(f"    ECM: {self.ecm.composition()}")
        print(f"    BBB: {self.vessel.bbb_tightness()}")


def build_region(name: str, factory: BrainRegionEcosystem) -> BrainRegion:
    """
    Client KHÔNG biết concrete factory nào — chỉ thấy interface.
    Đổi factory = đổi cả ecosystem, không sửa hàm này.
    """
    return BrainRegion(
        name=name,
        neuron=factory.create_principal_neuron(),
        glia=factory.create_supporting_glia(),
        ecm=factory.create_ecm(),
        vessel=factory.create_vasculature(),
    )


# =============================================================================
# E. ELLUMM VERSION — ModalityEcosystem
# =============================================================================

class MemoryUnit(ABC):
    modality: str
    @abstractmethod
    def signature(self) -> str: ...

class EmotionTag(ABC):
    modality: str
    @abstractmethod
    def valence_dim(self) -> str: ...

class ConsolidationPolicy(ABC):
    modality: str
    @abstractmethod
    def replay_when(self) -> str: ...

class RetrievalIndex(ABC):
    modality: str
    @abstractmethod
    def index_type(self) -> str: ...


# --- Visual family ---
class VisualMemoryUnit(MemoryUnit):
    modality = "visual"
    def signature(self): return "pixel-fingerprint + saccade-trace"

class VisualEmotionTag(EmotionTag):
    modality = "visual"
    def valence_dim(self): return "đẹp ↔ xấu / quen ↔ lạ"

class VisualConsolidationPolicy(ConsolidationPolicy):
    modality = "visual"
    def replay_when(self): return "REM sleep, hippocampal-cortical replay"

class VisualRetrievalIndex(RetrievalIndex):
    modality = "visual"
    def index_type(self): return "spatial-grid (V1 retinotopy + parahippocampal)"


# --- Auditory family ---
class AuditoryMemoryUnit(MemoryUnit):
    modality = "auditory"
    def signature(self): return "spectral envelope + temporal contour"

class AuditoryEmotionTag(EmotionTag):
    modality = "auditory"
    def valence_dim(self): return "vui ↔ buồn / yên ↔ động"

class AuditoryConsolidationPolicy(ConsolidationPolicy):
    modality = "auditory"
    def replay_when(self): return "NREM-2 sleep spindles"

class AuditoryRetrievalIndex(RetrievalIndex):
    modality = "auditory"
    def index_type(self): return "tonotopic (A1 frequency map)"


# --- Interoceptive family ---
class InteroceptiveMemoryUnit(MemoryUnit):
    modality = "interoceptive"
    def signature(self): return "hormone-vector + body-map"

class InteroceptiveEmotionTag(EmotionTag):
    modality = "interoceptive"
    def valence_dim(self): return "dễ chịu ↔ khó chịu / đói ↔ no"

class InteroceptiveConsolidationPolicy(ConsolidationPolicy):
    modality = "interoceptive"
    def replay_when(self): return "continuous, không phụ thuộc sleep stage"

class InteroceptiveRetrievalIndex(RetrievalIndex):
    modality = "interoceptive"
    def index_type(self): return "somatic cluster (insula body-map)"


class ModalityEcosystem(ABC):
    @abstractmethod
    def create_memory_unit(self): ...
    @abstractmethod
    def create_emotion_tag(self): ...
    @abstractmethod
    def create_consolidation_policy(self): ...
    @abstractmethod
    def create_retrieval_index(self): ...

class VisualEcosystem(ModalityEcosystem):
    def create_memory_unit(self):           return VisualMemoryUnit()
    def create_emotion_tag(self):           return VisualEmotionTag()
    def create_consolidation_policy(self):  return VisualConsolidationPolicy()
    def create_retrieval_index(self):       return VisualRetrievalIndex()

class AuditoryEcosystem(ModalityEcosystem):
    def create_memory_unit(self):           return AuditoryMemoryUnit()
    def create_emotion_tag(self):           return AuditoryEmotionTag()
    def create_consolidation_policy(self):  return AuditoryConsolidationPolicy()
    def create_retrieval_index(self):       return AuditoryRetrievalIndex()

class InteroceptiveEcosystem(ModalityEcosystem):
    def create_memory_unit(self):           return InteroceptiveMemoryUnit()
    def create_emotion_tag(self):           return InteroceptiveEmotionTag()
    def create_consolidation_policy(self):  return InteroceptiveConsolidationPolicy()
    def create_retrieval_index(self):       return InteroceptiveRetrievalIndex()


# =============================================================================
# DEMO
# =============================================================================

def demo() -> None:
    print("=" * 64)
    print("B+C. BUILD 3 BRAIN REGIONS — mỗi cái 1 ecosystem khác nhau")
    print("=" * 64)
    factories: list[tuple[str, BrainRegionEcosystem]] = [
        ("cortex_primary_visual",   CorticalEcosystem()),
        ("cerebellum_lobule_VI",    CerebellarEcosystem()),
        ("hippocampus_dentate",     HippocampalEcosystem()),
    ]
    for name, factory in factories:
        region = build_region(name, factory)
        region.operate()

    print()
    print("=" * 64)
    print("D. FAILURE — ép trộn họ (heterotopia)")
    print("=" * 64)
    print("  Lấy Pyramidal (cortex) + Bergmann glia (cerebellum) — sai họ")
    bad_region = BrainRegion(
        name="heterotopic_band",
        neuron=PyramidalNeuron(),
        glia=BergmannGlia(),         # ← SAI: Bergmann chỉ wrap Purkinje
        ecm=HippocampalECM(),        # ← SAI: ECM hippocampal không phù hợp
        vessel=CorticalBBB(),
    )
    try:
        bad_region.operate()
    except FamilyMismatch as e:
        print(f"  ✓ Bị chặn ngay: {e}")

    print()
    print("=" * 64)
    print("E. ELLUMM — ModalityEcosystem cho 3 modality")
    print("=" * 64)
    for label, mod_factory in [
        ("VISUAL", VisualEcosystem()),
        ("AUDITORY", AuditoryEcosystem()),
        ("INTEROCEPTIVE", InteroceptiveEcosystem()),
    ]:
        unit   = mod_factory.create_memory_unit()
        tag    = mod_factory.create_emotion_tag()
        policy = mod_factory.create_consolidation_policy()
        idx    = mod_factory.create_retrieval_index()
        print(f"\n  {label} family:")
        print(f"    MemoryUnit signature   : {unit.signature()}")
        print(f"    EmotionTag valence dim : {tag.valence_dim()}")
        print(f"    Consolidation replay   : {policy.replay_when()}")
        print(f"    RetrievalIndex type    : {idx.index_type()}")
        # Family integrity assertion: tất cả cùng modality
        assert unit.modality == tag.modality == policy.modality == idx.modality
    print("\n  ✓ Mọi family pass integrity check (cùng modality field).")

    print()
    print("=" * 64)
    print("MỞ RỘNG: thêm BasalGanglia ecosystem KHÔNG sửa code cũ")
    print("=" * 64)

    class MediumSpinyNeuronStriatal(PrincipalNeuron):
        region = "basal_ganglia"
        def fire(self): return "MSN burst → gating motor program"

    class StriatalAstrocyte(SupportingGlia):
        region = "basal_ganglia"
        def support(self, neuron):
            if neuron.region != self.region:
                raise FamilyMismatch(self, neuron)
            return "tonic dopamine clearance, K+ buffering, đặc thù striatum"

    class StriatalECM(ExtracellularMatrix):
        region = "basal_ganglia"
        def composition(self): return "perineuronal nets dày quanh fast-spiking interneurons"

    class StriatalBBB(Vasculature):
        region = "basal_ganglia"
        def bbb_tightness(self): return "tight, dopamine-sensitive transporters"

    class BasalGangliaEcosystem(BrainRegionEcosystem):
        def create_principal_neuron(self): return MediumSpinyNeuronStriatal()
        def create_supporting_glia(self):  return StriatalAstrocyte()
        def create_ecm(self):              return StriatalECM()
        def create_vasculature(self):      return StriatalBBB()

    new_region = build_region("basal_ganglia_putamen", BasalGangliaEcosystem())
    new_region.operate()
    print("\n  ✓ Code cũ không sửa dòng nào — Open-Closed về phía thêm family mới.")


if __name__ == "__main__":
    demo()


# =============================================================================
# THẢO LUẬN: TRADE-OFF ABSTRACT FACTORY
# =============================================================================
#
# DỄ:  thêm family mới (BasalGangliaEcosystem) — không sửa interface, không
#      sửa client, không sửa family cũ.
#
# KHÓ: thêm product type mới (vd: thêm `create_neuromodulator_input`). Phải:
#      - Sửa interface BrainRegionEcosystem (+ 1 abstract method)
#      - Sửa cả 4 concrete factory (Cortical, Cerebellar, Hippocampal, BasalGanglia)
#      - Phá compatibility với code đã chạy ổn định
#
# Đây là "trục đối xứng ngược" giữa Abstract Factory và Factory Method:
#
#                              dễ thêm     khó thêm
#       Factory Method         product     product type
#       Abstract Factory       family      product type
#
# (Cả hai đều khó thêm product type — nhưng Abstract Factory đau hơn nhiều
#  vì có nhiều factory phải sửa cùng lúc.)
#
# ARCHITECT QUYẾT ĐỊNH: dự đoán hướng mở rộng nào sẽ xảy ra.
#   - Domain UI theme: nhiều theme (family) sẽ thêm, ít loại widget mới  → Abstract Factory.
#   - Domain xử lý event: nhiều loại event (product) sẽ thêm, ít platform → Factory Method.
#
# Khi chiều product nhiều và muốn linh hoạt cả hai chiều, cân nhắc:
#   - Builder (lesson 04) — composition runtime, không cần family cố định.
#   - Registry-based factory — dispatch table runtime thay vì class hierarchy.
#   - Prototype (lesson 05) — clone từ template thay vì tạo từ class.
"""
"""
