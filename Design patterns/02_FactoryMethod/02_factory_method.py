"""
Lesson 02 — Factory Method Pattern
Ví dụ neuroscience: Neural Stem Cell (NSC) ở các vùng não khác nhau biệt hóa
thành các loại neuron khác nhau, dù dùng cùng một quy trình phát triển
(divide → migrate → form synapses).

File này triển khai 4 phần:
    A. ANTI-PATTERN — Simple Factory với if-else (để cảm nhận nỗi đau)
    B. FACTORY METHOD — đầy đủ GoF
    C. PHIÊN BẢN PYTHONIC — dùng class attribute thay cho method override
    D. DEMO FAILURE — quên override → fail-fast với NotImplementedError
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Type


# =============================================================================
# PRODUCT HIERARCHY — các loại neuron
# =============================================================================

class Neuron(ABC):
    """Interface chung cho mọi loại neuron."""

    @abstractmethod
    def neurotransmitter(self) -> str: ...

    @abstractmethod
    def fire(self) -> str: ...

    def migrate(self) -> None:
        # Logic di trú chung — radial glia guidance
        # (đơn giản hóa: chỉ in ra)
        print(f"  · {self.__class__.__name__} migrates along radial glia")

    def form_synapses(self) -> None:
        print(f"  · {self.__class__.__name__} forms synapses, NT = {self.neurotransmitter()}")


class GlutamatergicNeuron(Neuron):
    """Neuron kích thích, đa số ở cortex layers 2-6 và hippocampus."""
    def neurotransmitter(self) -> str:
        return "glutamate"
    def fire(self) -> str:
        return "EPSP — excitatory postsynaptic potential"


class GABAergicInterneuron(Neuron):
    """Interneuron ức chế, phần lớn xuất phát từ medial/lateral ganglionic eminence."""
    def neurotransmitter(self) -> str:
        return "GABA"
    def fire(self) -> str:
        return "IPSP — inhibitory postsynaptic potential"


class GranuleCell(Neuron):
    """Tế bào hạt cerebellum, sinh ra từ rhombic lip (Atoh1+)."""
    def neurotransmitter(self) -> str:
        return "glutamate"
    def fire(self) -> str:
        return "parallel fiber burst"


class MediumSpinyNeuron(Neuron):
    """Neuron chính của striatum (basal ganglia), ức chế."""
    def neurotransmitter(self) -> str:
        return "GABA"
    def fire(self) -> str:
        return "MSN burst — gating motor program"


# =============================================================================
# A. ANTI-PATTERN — Simple Factory với if-else
# =============================================================================
# Vấn đề: thêm 1 vùng não mới = sửa hàm này. Vi phạm Open-Closed Principle.
# Khi danh sách vùng não tăng đến 10-20, hàm này thành "thượng đế function".

def develop_anti_pattern(region_name: str) -> Neuron:
    if region_name == "dorsal_forebrain":
        neuron: Neuron = GlutamatergicNeuron()
    elif region_name == "ventral_forebrain":
        neuron = GABAergicInterneuron()
    elif region_name == "cerebellum_rhombic_lip":
        neuron = GranuleCell()
    elif region_name == "striatum":
        neuron = MediumSpinyNeuron()
    else:
        raise ValueError(f"Unknown region: {region_name}")

    # Code chung — bị duplicate khắp nơi nếu nhiều function tương tự
    neuron.migrate()
    neuron.form_synapses()
    return neuron


# =============================================================================
# B. FACTORY METHOD — đầy đủ GoF
# =============================================================================

class NeuralStemCell(ABC):
    """
    Creator abstract.
    differentiate() là TEMPLATE METHOD chung cho mọi NSC.
    create_neuron() là FACTORY METHOD — subclass override.
    """

    def differentiate(self) -> Neuron:
        # Template logic — viết đúng 1 lần, không sửa khi thêm vùng não mới
        neuron = self.create_neuron()      # ← factory method
        neuron.migrate()
        neuron.form_synapses()
        return neuron

    @abstractmethod
    def create_neuron(self) -> Neuron:
        """Subclass quyết định loại neuron cụ thể."""
        ...

    @property
    @abstractmethod
    def region_name(self) -> str: ...


class DorsalForebrainNSC(NeuralStemCell):
    region_name = "dorsal_forebrain (Pax6+, BMP-high)"

    def create_neuron(self) -> Neuron:
        return GlutamatergicNeuron()


class VentralForebrainNSC(NeuralStemCell):
    region_name = "ventral_forebrain (Nkx2.1+, Shh-high)"

    def create_neuron(self) -> Neuron:
        return GABAergicInterneuron()


class CerebellumRhombicLipNSC(NeuralStemCell):
    region_name = "cerebellum_rhombic_lip (Atoh1+)"

    def create_neuron(self) -> Neuron:
        return GranuleCell()


class StriatalNSC(NeuralStemCell):
    region_name = "lateral_ganglionic_eminence → striatum"

    def create_neuron(self) -> Neuron:
        return MediumSpinyNeuron()


# =============================================================================
# C. PHIÊN BẢN PYTHONIC — class attribute thay cho method
# =============================================================================
# Khi factory method chỉ là "trả về 1 class cụ thể, không tham số động",
# có thể dùng class attribute. Ngắn hơn, vẫn giữ tinh thần Factory Method
# (subclass khai báo thay vì client chọn).

class NeuralStemCellLite(ABC):
    neuron_class: Type[Neuron]                 # subclass khai báo
    region_name: str

    def differentiate(self) -> Neuron:
        neuron = self.neuron_class()           # ← factory "method" rút gọn
        neuron.migrate()
        neuron.form_synapses()
        return neuron


class HippocampalNSC(NeuralStemCellLite):
    neuron_class = GlutamatergicNeuron
    region_name = "hippocampal_dentate_gyrus (adult neurogenesis)"


class OlfactoryBulbNSC(NeuralStemCellLite):
    neuron_class = GABAergicInterneuron
    region_name = "subventricular_zone → olfactory_bulb"


# =============================================================================
# D. DEMO FAILURE — quên override → fail-fast
# =============================================================================

class BrokenNSC(NeuralStemCell):
    """Subclass quên override create_neuron — sẽ fail khi instantiate."""
    region_name = "broken_region"
    # KHÔNG override create_neuron!


# =============================================================================
# DEMO
# =============================================================================

def demo() -> None:
    print("=" * 64)
    print("A. ANTI-PATTERN — if-else trong code chung")
    print("=" * 64)
    n = develop_anti_pattern("dorsal_forebrain")
    print(f"  Output: {n.__class__.__name__} fires '{n.fire()}'")
    print("  ⚠️  Thêm vùng mới = sửa hàm develop_anti_pattern.")

    print()
    print("=" * 64)
    print("B. FACTORY METHOD — full GoF")
    print("=" * 64)
    nscs: list[NeuralStemCell] = [
        DorsalForebrainNSC(),
        VentralForebrainNSC(),
        CerebellumRhombicLipNSC(),
        StriatalNSC(),
    ]
    for nsc in nscs:
        print(f"\n  NSC ở {nsc.region_name}:")
        neuron = nsc.differentiate()
        print(f"  → Sinh ra {neuron.__class__.__name__} với firing '{neuron.fire()}'")

    print()
    print("=" * 64)
    print("C. PHIÊN BẢN PYTHONIC — class attribute")
    print("=" * 64)
    for nsc_lite in [HippocampalNSC(), OlfactoryBulbNSC()]:
        print(f"\n  NSC ở {nsc_lite.region_name}:")
        neuron = nsc_lite.differentiate()
        print(f"  → Sinh ra {neuron.__class__.__name__}")

    print()
    print("=" * 64)
    print("D. DEMO FAILURE — quên override")
    print("=" * 64)
    try:
        broken = BrokenNSC()
        broken.differentiate()
    except TypeError as e:
        print(f"  ✓ ABCMeta chặn ngay khi instantiate:")
        print(f"    TypeError: {e}")
        print("  → Fail-fast: lỗi xuất hiện đúng nơi sai (khởi tạo subclass thiếu),")
        print("    không lan ra runtime sâu trong hệ thống.")

    print()
    print("=" * 64)
    print("MỞ RỘNG KHÔNG SỬA — minh họa Open-Closed")
    print("=" * 64)
    # Thêm 1 vùng não mới — KHÔNG sửa NeuralStemCell, KHÔNG sửa code đã có
    class SpinalCordVentralNSC(NeuralStemCell):
        region_name = "spinal_cord_ventral (Olig2+, Shh-high)"

        def create_neuron(self) -> Neuron:
            # Tạo motor neuron — định nghĩa inline cho gọn demo
            class MotorNeuron(Neuron):
                def neurotransmitter(self) -> str: return "acetylcholine"
                def fire(self) -> str: return "alpha-motor-neuron volley → muscle contraction"
            return MotorNeuron()

    new_nsc = SpinalCordVentralNSC()
    print(f"  Thêm class mới SpinalCordVentralNSC ({new_nsc.region_name}):")
    motor = new_nsc.differentiate()
    print(f"  → {motor.__class__.__name__} fires '{motor.fire()}'")
    print("  ✓ Code cũ không bị đụng đến — đó là Open-Closed Principle.")


if __name__ == "__main__":
    demo()


# =============================================================================
# THẢO LUẬN: KHI NÀO DÙNG, KHI NÀO KHÔNG?
# =============================================================================
#
# DÙNG Factory Method khi:
#   - Có một thuật toán/quy trình chung (template) gọi một bước "tạo object"
#     mà loại object phụ thuộc vào ngữ cảnh.
#   - Bạn muốn cho phép mở rộng số lượng loại sản phẩm mà không sửa code
#     của client (Open-Closed).
#   - Loại object cần tạo phụ thuộc vào subclass nào của Creator đang chạy.
#
# KHÔNG DÙNG khi:
#   - Chỉ có 1-2 loại sản phẩm và rất ít khi mở rộng → hardcode đơn giản hơn.
#   - Bạn cần tạo nguyên một họ object (neuron + glia + ECM) khớp nhau:
#     dùng ABSTRACT FACTORY (lesson 03), Factory Method không đủ.
#   - Việc "chọn loại object" phụ thuộc vào tham số runtime, không phải
#     subclass: dùng STRATEGY (lesson 21) hoặc registry/dispatch table.
#
# QUY TẮC NGÓN TAY CÁI:
#   "Khi bạn thấy if-else dài chọn class theo tham số, đó là Factory Method
#    đang muốn được sinh ra."
"""
"""
