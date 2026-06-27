"""
Lesson 04 — Builder Pattern
Ví dụ neuroscience: synaptogenesis lắp ráp synapse qua các bước có thứ tự
(adhesion → active zone → vesicle → PSD → receptor → astrocyte ensheath),
mỗi bước có thể tùy biến → cùng quy trình tạo nhiều loại synapse khác nhau.

File này triển khai 5 phần:
    A. ANTI-PATTERN constructor monster (15 tham số)
    B. Product immutable: Synapse (frozen dataclass)
    C. Fluent SynapseBuilder với cross-component validation
    D. SynapseDirector đóng gói 4 preset
    E. Ellumm version: MemoryEpisodeBuilder
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# A. ANTI-PATTERN — constructor monster
# =============================================================================
# Để cảm nhận nỗi đau: 15 tham số, không nhớ thứ tự, mặc định lung tung.

class SynapseAntiPattern:
    def __init__(
        self, presynaptic, postsynaptic, neurexin_type=None, neuroligin_type=None,
        active_zone_proteins=None, vesicle_count=0, neurotransmitter="glutamate",
        psd_scaffold=None, ampa_count=0, nmda_count=0, gaba_a_count=0,
        kainate_count=0, has_astrocyte=False, is_silent=False, is_electrical=False
    ):
        # Không validate gì — caller phải tự lo
        # Nếu psd_scaffold=PSD-95 và gaba_a_count>0 thì sai sinh học
        # nhưng không có gì chặn.
        ...
        # 15 tham số → 15 cách truyền nhầm.


# =============================================================================
# B. PRODUCT immutable
# =============================================================================

class SynapseInvalid(Exception):
    """Raise khi cross-component validation thất bại tại build()."""


@dataclass(frozen=True)
class Synapse:
    """
    Product cuối cùng — immutable. Chỉ tạo qua Builder để đảm bảo invariant.

    Invariants (đảm bảo bởi Builder.build()):
        - Có axon_contact (presynaptic + postsynaptic + adhesion molecules)
        - Nếu PSD = PSD-95 → receptors phải là glutamatergic (AMPA/NMDA)
        - Nếu PSD = Gephyrin → receptors phải là GABA-A
        - Nếu is_electrical=True → không có vesicle/receptor (gap junction)
        - is_silent: chỉ NMDA, không có AMPA → hợp lệ nhưng không phát ngay
    """
    presynaptic: str
    postsynaptic: str
    neurexin_type: Optional[str]      # ví dụ "1β", "2", None nếu electrical
    neuroligin_type: Optional[str]    # ví dụ "1", "2", None nếu electrical
    vesicle_count: int                # số docking site (0 nếu electrical)
    neurotransmitter: Optional[str]   # "glutamate", "GABA", None nếu electrical
    psd_scaffold: Optional[str]       # "PSD-95", "Gephyrin", None nếu electrical
    ampa_count: int
    nmda_count: int
    gaba_a_count: int
    has_astrocyte: bool
    is_silent: bool
    is_electrical: bool

    def fire(self) -> str:
        if self.is_electrical:
            return f"electrical coupling pre↔post via gap junction"
        if self.is_silent:
            return "silent synapse — only NMDA, no immediate signaling"
        if self.neurotransmitter == "glutamate":
            return f"EPSP via {self.ampa_count} AMPA + {self.nmda_count} NMDA"
        if self.neurotransmitter == "GABA":
            return f"IPSP via {self.gaba_a_count} GABA-A"
        return "no transmitter"


# =============================================================================
# C. FLUENT BUILDER với cross-component validation
# =============================================================================

class SynapseBuilder:
    def __init__(self, presynaptic: str, postsynaptic: str):
        # Bắt buộc: tối thiểu là pre + post neuron
        self._presynaptic = presynaptic
        self._postsynaptic = postsynaptic
        self._neurexin: Optional[str] = None
        self._neuroligin: Optional[str] = None
        self._vesicle_count: int = 0
        self._neurotransmitter: Optional[str] = None
        self._psd: Optional[str] = None
        self._ampa: int = 0
        self._nmda: int = 0
        self._gaba_a: int = 0
        self._has_astrocyte: bool = False
        self._is_silent: bool = False
        self._is_electrical: bool = False

    # --- Mỗi bước build trả về self (fluent / chainable) ---

    def with_chemical_adhesion(self, neurexin: str, neuroligin: str) -> "SynapseBuilder":
        # Validate pair-level: neurexin chỉ pair với neuroligin tương thích
        valid_pairs = {
            ("1β", "1"): "excitatory",
            ("1α", "1"): "excitatory",
            ("2", "2"): "inhibitory",
            ("3", "2"): "inhibitory",
        }
        if (neurexin, neuroligin) not in valid_pairs:
            raise SynapseInvalid(
                f"Neurexin-{neurexin} không pair với neuroligin-{neuroligin}. "
                f"Cặp hợp lệ: {list(valid_pairs.keys())}"
            )
        self._neurexin = neurexin
        self._neuroligin = neuroligin
        return self

    def with_active_zone(self, vesicle_count: int, neurotransmitter: str) -> "SynapseBuilder":
        if vesicle_count < 1:
            raise SynapseInvalid("vesicle_count phải ≥ 1 cho synapse hóa học")
        if neurotransmitter not in {"glutamate", "GABA", "ACh", "dopamine"}:
            raise SynapseInvalid(f"Neurotransmitter '{neurotransmitter}' không hỗ trợ ở demo")
        self._vesicle_count = vesicle_count
        self._neurotransmitter = neurotransmitter
        return self

    def with_psd(self, scaffold: str) -> "SynapseBuilder":
        if scaffold not in {"PSD-95", "Gephyrin"}:
            raise SynapseInvalid(f"Scaffold '{scaffold}' không hỗ trợ")
        self._psd = scaffold
        return self

    def with_glutamate_receptors(self, ampa: int = 0, nmda: int = 0) -> "SynapseBuilder":
        if ampa < 0 or nmda < 0:
            raise SynapseInvalid("Số receptor không âm")
        self._ampa = ampa
        self._nmda = nmda
        return self

    def with_gaba_a_receptors(self, count: int) -> "SynapseBuilder":
        if count < 1:
            raise SynapseInvalid("GABA-A count phải ≥ 1")
        self._gaba_a = count
        return self

    def with_astrocyte_ensheath(self) -> "SynapseBuilder":
        self._has_astrocyte = True
        return self

    def as_silent(self) -> "SynapseBuilder":
        """Synapse 'silent' — chỉ NMDA, chưa unsilenced."""
        self._is_silent = True
        return self

    def as_electrical_gap_junction(self) -> "SynapseBuilder":
        """Gap junction — không có vesicle, receptor, PSD."""
        self._is_electrical = True
        return self

    # --- BUILD: cross-component validation + tạo Product immutable ---

    def build(self) -> Synapse:
        # Electrical = bypass tất cả constraint hóa học
        if self._is_electrical:
            return Synapse(
                presynaptic=self._presynaptic, postsynaptic=self._postsynaptic,
                neurexin_type=None, neuroligin_type=None, vesicle_count=0,
                neurotransmitter=None, psd_scaffold=None,
                ampa_count=0, nmda_count=0, gaba_a_count=0,
                has_astrocyte=False, is_silent=False, is_electrical=True,
            )

        # Chemical synapse — tất cả constraint phải pass
        if self._neurexin is None:
            raise SynapseInvalid("Chemical synapse cần adhesion (neurexin-neuroligin)")
        if self._vesicle_count == 0:
            raise SynapseInvalid("Chemical synapse cần active zone với vesicle")
        if self._psd is None:
            raise SynapseInvalid("Chemical synapse cần PSD scaffold")

        # Cross-component: PSD ↔ neurotransmitter ↔ receptor consistency
        if self._psd == "PSD-95":
            if self._neurotransmitter != "glutamate":
                raise SynapseInvalid(
                    f"PSD-95 đi với glutamate, không phải '{self._neurotransmitter}'"
                )
            if self._gaba_a > 0:
                raise SynapseInvalid("PSD-95 không neo GABA-A receptor (dùng Gephyrin)")
            if self._ampa == 0 and self._nmda == 0:
                raise SynapseInvalid("Glutamatergic synapse cần ≥ 1 AMPA hoặc NMDA")

        if self._psd == "Gephyrin":
            if self._neurotransmitter != "GABA":
                raise SynapseInvalid(
                    f"Gephyrin đi với GABA, không phải '{self._neurotransmitter}'"
                )
            if self._ampa > 0 or self._nmda > 0:
                raise SynapseInvalid("Gephyrin không neo AMPA/NMDA (dùng PSD-95)")
            if self._gaba_a == 0:
                raise SynapseInvalid("GABAergic synapse cần ≥ 1 GABA-A")

        # Silent synapse: phải có NMDA, KHÔNG có AMPA
        if self._is_silent:
            if self._nmda == 0:
                raise SynapseInvalid("Silent synapse cần NMDA receptor")
            if self._ampa > 0:
                raise SynapseInvalid("Silent synapse không có AMPA (đó là 'unsilenced')")

        return Synapse(
            presynaptic=self._presynaptic, postsynaptic=self._postsynaptic,
            neurexin_type=self._neurexin, neuroligin_type=self._neuroligin,
            vesicle_count=self._vesicle_count, neurotransmitter=self._neurotransmitter,
            psd_scaffold=self._psd, ampa_count=self._ampa, nmda_count=self._nmda,
            gaba_a_count=self._gaba_a, has_astrocyte=self._has_astrocyte,
            is_silent=self._is_silent, is_electrical=False,
        )


# =============================================================================
# D. DIRECTOR — đóng gói preset
# =============================================================================

class SynapseDirector:
    """
    Director đóng gói các 'recipe' phổ biến.
    Client gọi build_excitatory_glutamatergic() thay vì nhớ chuỗi step.
    """

    @staticmethod
    def build_excitatory_glutamatergic(pre: str, post: str) -> Synapse:
        return (SynapseBuilder(pre, post)
            .with_chemical_adhesion(neurexin="1β", neuroligin="1")
            .with_active_zone(vesicle_count=12, neurotransmitter="glutamate")
            .with_psd("PSD-95")
            .with_glutamate_receptors(ampa=8, nmda=4)
            .with_astrocyte_ensheath()
            .build())

    @staticmethod
    def build_inhibitory_gabaergic(pre: str, post: str) -> Synapse:
        return (SynapseBuilder(pre, post)
            .with_chemical_adhesion(neurexin="2", neuroligin="2")
            .with_active_zone(vesicle_count=8, neurotransmitter="GABA")
            .with_psd("Gephyrin")
            .with_gaba_a_receptors(count=12)
            .build())

    @staticmethod
    def build_silent_synapse(pre: str, post: str) -> Synapse:
        """Synapse glutamatergic chỉ có NMDA — chưa unsilenced (chưa có AMPA)."""
        return (SynapseBuilder(pre, post)
            .with_chemical_adhesion(neurexin="1β", neuroligin="1")
            .with_active_zone(vesicle_count=10, neurotransmitter="glutamate")
            .with_psd("PSD-95")
            .with_glutamate_receptors(ampa=0, nmda=4)
            .as_silent()
            .build())

    @staticmethod
    def build_electrical_gap_junction(pre: str, post: str) -> Synapse:
        return (SynapseBuilder(pre, post)
            .as_electrical_gap_junction()
            .build())


# =============================================================================
# E. ELLUMM — MemoryEpisodeBuilder
# =============================================================================

@dataclass(frozen=True)
class MemoryEpisode:
    emotion_vector: dict             # bắt buộc
    salience_score: float            # bắt buộc
    visual_snapshot: Optional[str] = None
    auditory_snippet: Optional[str] = None
    spatial_temporal: Optional[dict] = None
    olfactory_trace: Optional[str] = None
    consolidation_flags: dict = field(default_factory=dict)


class EpisodeInvalid(Exception): ...


class MemoryEpisodeBuilder:
    def __init__(self):
        self._emotion: Optional[dict] = None
        self._salience: Optional[float] = None
        self._visual: Optional[str] = None
        self._auditory: Optional[str] = None
        self._spatial: Optional[dict] = None
        self._olfactory: Optional[str] = None
        self._flags: dict = {}

    def with_emotion(self, emotion: dict) -> "MemoryEpisodeBuilder":
        if not all(k in emotion for k in ("arousal", "valence")):
            raise EpisodeInvalid("Emotion vector cần arousal + valence tối thiểu")
        self._emotion = emotion
        return self

    def with_salience(self, score: float) -> "MemoryEpisodeBuilder":
        if not 0.0 <= score <= 1.0:
            raise EpisodeInvalid("Salience score phải ∈ [0, 1]")
        self._salience = score
        return self

    def with_visual(self, snapshot: str) -> "MemoryEpisodeBuilder":
        self._visual = snapshot
        return self

    def with_auditory(self, snippet: str) -> "MemoryEpisodeBuilder":
        self._auditory = snippet
        return self

    def with_spatial_temporal(self, ctx: dict) -> "MemoryEpisodeBuilder":
        if "place_cell_signature" not in ctx:
            raise EpisodeInvalid("Spatial-temporal context cần place_cell_signature")
        self._spatial = ctx
        return self

    def with_olfactory(self, trace: str) -> "MemoryEpisodeBuilder":
        self._olfactory = trace
        return self

    def flag_consolidated(self, sleep_stage: str) -> "MemoryEpisodeBuilder":
        self._flags["consolidated_in"] = sleep_stage
        return self

    def build(self) -> MemoryEpisode:
        if self._emotion is None:
            raise EpisodeInvalid("Mọi episode phải có emotion_vector")
        if self._salience is None:
            raise EpisodeInvalid("Mọi episode phải có salience_score")
        # High-salience episode nên có ít nhất 1 modality input thực
        if self._salience > 0.8 and not (self._visual or self._auditory or self._olfactory):
            raise EpisodeInvalid(
                "High-salience episode (>0.8) cần ít nhất 1 modality input cụ thể"
            )
        return MemoryEpisode(
            emotion_vector=self._emotion,
            salience_score=self._salience,
            visual_snapshot=self._visual,
            auditory_snippet=self._auditory,
            spatial_temporal=self._spatial,
            olfactory_trace=self._olfactory,
            consolidation_flags=dict(self._flags),
        )


# =============================================================================
# DEMO
# =============================================================================

def demo() -> None:
    print("=" * 64)
    print("C+D. SYNAPSE BUILDER — 4 preset qua Director")
    print("=" * 64)
    director = SynapseDirector()
    syn1 = director.build_excitatory_glutamatergic("L4_neuron_A", "L2_neuron_B")
    syn2 = director.build_inhibitory_gabaergic("PV_interneuron", "L5_pyramidal")
    syn3 = director.build_silent_synapse("CA3_pyramidal", "CA1_pyramidal")
    syn4 = director.build_electrical_gap_junction("CA1_interneuron_A", "CA1_interneuron_B")

    for i, s in enumerate([syn1, syn2, syn3, syn4], 1):
        print(f"\n  Synapse {i} ({s.presynaptic} → {s.postsynaptic}):")
        print(f"    Type: PSD={s.psd_scaffold}, NT={s.neurotransmitter}, "
              f"silent={s.is_silent}, electrical={s.is_electrical}")
        print(f"    Fire: {s.fire()}")

    print()
    print("=" * 64)
    print("FLUENT BUILDER — custom synapse với chaining")
    print("=" * 64)
    custom = (SynapseBuilder("VTA_dopamine_neuron", "NAc_MSN")
        .with_chemical_adhesion(neurexin="1β", neuroligin="1")
        .with_active_zone(vesicle_count=6, neurotransmitter="glutamate")
        .with_psd("PSD-95")
        .with_glutamate_receptors(ampa=2, nmda=2)  # ít AMPA — VTA ít glutamate co-release
        .build())
    print(f"  VTA→NAc co-release synapse: {custom.fire()}")

    print()
    print("=" * 64)
    print("FAILURE — cố trộn PSD-95 với GABA-A (sai sinh học)")
    print("=" * 64)
    try:
        bad = (SynapseBuilder("X", "Y")
            .with_chemical_adhesion(neurexin="2", neuroligin="2")
            .with_active_zone(vesicle_count=10, neurotransmitter="GABA")
            .with_psd("PSD-95")                # SAI: PSD-95 cho glutamatergic
            .with_gaba_a_receptors(count=10)
            .build())
    except SynapseInvalid as e:
        print(f"  ✓ Bị chặn ngay tại build(): {e}")

    print()
    print("=" * 64)
    print("FAILURE — silent synapse với AMPA (mâu thuẫn)")
    print("=" * 64)
    try:
        bad2 = (SynapseBuilder("A", "B")
            .with_chemical_adhesion(neurexin="1β", neuroligin="1")
            .with_active_zone(vesicle_count=8, neurotransmitter="glutamate")
            .with_psd("PSD-95")
            .with_glutamate_receptors(ampa=4, nmda=4)
            .as_silent()                        # SAI: silent = không AMPA
            .build())
    except SynapseInvalid as e:
        print(f"  ✓ Bị chặn ngay: {e}")

    print()
    print("=" * 64)
    print("E. ELLUMM — MemoryEpisode với optional modality")
    print("=" * 64)

    # Episode 1: high-salience event (rắn) — có visual + auditory + spatial
    ep1 = (MemoryEpisodeBuilder()
        .with_emotion({"arousal": 92, "valence": -45, "cortisol": 78})
        .with_salience(0.95)
        .with_visual("snake_curvy_pattern_120px_low_in_frame")
        .with_auditory("hiss_2.4kHz_burst")
        .with_spatial_temporal({"place_cell_signature": "garden_path_node_3", "t": 1733120000})
        .build())
    print(f"  Episode 1 (snake): salience={ep1.salience_score}, modalities="
          f"{[m for m in ['visual','auditory','spatial','olfactory'] if getattr(ep1, m+('_snippet' if m=='auditory' else '_snapshot' if m=='visual' else '_temporal' if m=='spatial' else '_trace'))]}")

    # Episode 2: dreaming (không visual hiện tại, không spatial)
    ep2 = (MemoryEpisodeBuilder()
        .with_emotion({"arousal": 35, "valence": 10, "cortisol": 12})
        .with_salience(0.4)
        .build())
    print(f"  Episode 2 (drifting thought): salience={ep2.salience_score}, "
          f"visual={ep2.visual_snapshot}, spatial={ep2.spatial_temporal}")

    # Episode 3: thử build high-salience không có modality → fail
    print("\n  Thử build episode high-salience (0.9) không có modality input:")
    try:
        ep3 = (MemoryEpisodeBuilder()
            .with_emotion({"arousal": 80, "valence": -20})
            .with_salience(0.9)               # cao nhưng không có modality
            .build())
    except EpisodeInvalid as e:
        print(f"  ✓ Bị chặn: {e}")


if __name__ == "__main__":
    demo()


# =============================================================================
# THẢO LUẬN: BUILDER vs ALTERNATIVE
# =============================================================================
#
# Trong Python, có 2 alternative mạnh cho Builder:
#
# 1) DATACLASS + KEYWORD ARGS + __post_init__ VALIDATION
#    @dataclass(frozen=True)
#    class Synapse:
#        ...
#        def __post_init__(self):
#            if self.psd_scaffold == "PSD-95" and self.gaba_a_count > 0:
#                raise SynapseInvalid(...)
#
#    Ưu: gọn, Pythonic, IDE autocomplete tốt.
#    Nhược: caller phải nhớ tên 12 kwargs, không có chaining, không có preset.
#    Khi nào dùng: object có ≤ 8 field, ít invariant phức tạp, không có preset.
#
# 2) FACTORY FUNCTIONS
#    def make_excitatory_synapse(pre, post): return Synapse(...)
#    def make_inhibitory_synapse(pre, post): return Synapse(...)
#
#    Đây thực ra là Director không có Builder bên dưới — chỉ phù hợp khi
#    không cần tùy biến giữa các preset.
#
# KHI BUILDER THỰC SỰ TỎA SÁNG:
#   - Có > 4 field optional
#   - Có invariant cross-field phức tạp (như PSD ↔ NT ↔ receptor)
#   - Có nhiều preset cần đóng gói (Director)
#   - Cần fluent API cho DSL-like syntax (SQL builder, GraphQL, test setup)
#   - Cần immutable Product với validation tập trung
#
# QUY TẮC: nếu __post_init__ của bạn dài hơn 5 dòng và phải xử lý nhiều
# combo, đó là tín hiệu Builder đang muốn được sinh ra.
"""
"""
