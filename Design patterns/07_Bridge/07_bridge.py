"""
Lesson 07 — Bridge Pattern
Ví dụ neuroscience: visual system tách "loại information" (form/color/motion)
khỏi "pathway dẫn truyền" (parvocellular/magnocellular/koniocellular).
Cả 2 dimension biến đổi độc lập → tránh Cartesian class explosion.

Bằng chứng sinh học cho decoupling:
    - Achromatopsia (V4 lesion): mất color, form/motion còn nguyên
    - Akinetopsia (V5/MT lesion): mất motion, form/color còn nguyên

File này triển khai 7 phần:
    A. ANTI-PATTERN — inheritance Cartesian explosion (3 × 3 = 9 class)
    B. IMPLEMENTOR hierarchy: Pathway + 3 concrete
    C. ABSTRACTION hierarchy: VisualInformation + 3 concrete
    D. Demo runtime swap pathway
    E. Demo achromatopsia / akinetopsia
    F. Mở rộng: thêm SuperiorColliculusPathway không sửa Abstraction
    G. Ellumm: MemoryOperation × StorageBackend
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# A. ANTI-PATTERN — Cartesian explosion với inheritance
# =============================================================================
# Chỉ minh họa nỗi đau. KHÔNG nên dùng pattern này trong thực tế.
# Mỗi class có 2 trục nén vào: loại info × pathway type.

class FormViaParvocellular_AntiPattern: ...
class FormViaMagnocellular_AntiPattern: ...
class FormViaKoniocellular_AntiPattern: ...
class ColorViaParvocellular_AntiPattern: ...
class ColorViaMagnocellular_AntiPattern: ...
class ColorViaKoniocellular_AntiPattern: ...
class MotionViaParvocellular_AntiPattern: ...
class MotionViaMagnocellular_AntiPattern: ...
class MotionViaKoniocellular_AntiPattern: ...
# Thêm Depth → +3 class. Thêm Superior Colliculus pathway → +3 class.
# Tổ hợp bùng nổ.


# =============================================================================
# Domain types
# =============================================================================

@dataclass
class VisualScene:
    """Input thô từ retina/LGN — gồm các thành phần feature mức thấp."""
    edges_and_contours: list[tuple[float, float]]    # cho form
    color_channels: dict[str, float]                  # 'red_green', 'blue_yellow', 'luminance'
    frame_diff: list[float]                           # cho motion
    binocular_disparity: float = 0.0


@dataclass
class ProcessedSignal:
    """Output sau khi pathway xử lý — spike train + metadata."""
    spikes: list[float]
    latency_ms: int
    spatial_resolution: str    # 'high', 'medium', 'low'
    pathway_name: str


# =============================================================================
# B. IMPLEMENTOR hierarchy — Pathway
# =============================================================================

class Pathway(ABC):
    """Implementor abstract — tách khỏi VisualInformation."""

    @abstractmethod
    def process(self, feature: list[float]) -> ProcessedSignal: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class ParvocellularPathway(Pathway):
    """High spatial resolution, color-sensitive, slow (~30ms).
    LGN layer 3-6 → V1 layer 4Cβ → V2 thin stripes → V4."""
    name = "parvocellular"

    def process(self, feature: list[float]) -> ProcessedSignal:
        # Mô phỏng: high-resolution xử lý chậm
        spikes = [v * 1.0 for v in feature]    # giữ chi tiết nguyên
        return ProcessedSignal(
            spikes=spikes, latency_ms=30,
            spatial_resolution="high", pathway_name=self.name,
        )


class MagnocellularPathway(Pathway):
    """Low spatial resolution, color-blind, motion-sensitive, fast (~15ms).
    LGN layer 1-2 → V1 layer 4Cα → V2 thick stripes → V5/MT."""
    name = "magnocellular"

    def process(self, feature: list[float]) -> ProcessedSignal:
        # Mô phỏng: low-resolution (averaging) nhưng nhanh
        if not feature:
            return ProcessedSignal([], 15, "low", self.name)
        avg_chunks = []
        chunk_size = max(1, len(feature) // 4)
        for i in range(0, len(feature), chunk_size):
            chunk = feature[i:i + chunk_size]
            avg_chunks.append(sum(chunk) / len(chunk))
        return ProcessedSignal(
            spikes=avg_chunks, latency_ms=15,
            spatial_resolution="low", pathway_name=self.name,
        )


class KoniocellularPathway(Pathway):
    """Blue-yellow color, smaller cells, intermediate speed.
    LGN K-layers (between principal layers) → V1 blobs."""
    name = "koniocellular"

    def process(self, feature: list[float]) -> ProcessedSignal:
        spikes = [v * 0.7 for v in feature]    # gain thấp hơn P
        return ProcessedSignal(
            spikes=spikes, latency_ms=22,
            spatial_resolution="medium", pathway_name=self.name,
        )


# =============================================================================
# C. ABSTRACTION hierarchy — VisualInformation
# =============================================================================

class VisualInformation(ABC):
    """Abstraction — giữ ref tới Pathway qua composition (Bridge!)."""

    def __init__(self, pathway: Pathway):
        self._pathway = pathway

    def set_pathway(self, pathway: Pathway) -> None:
        """Cho phép swap pathway runtime — attentional re-routing."""
        self._pathway = pathway

    def extract(self, scene: VisualScene) -> ProcessedSignal:
        """Template method: chọn feature → pathway xử lý."""
        feature = self._select_feature(scene)
        return self._pathway.process(feature)

    @abstractmethod
    def _select_feature(self, scene: VisualScene) -> list[float]: ...

    @property
    @abstractmethod
    def info_type(self) -> str: ...


class FormInformation(VisualInformation):
    info_type = "form"
    def _select_feature(self, scene: VisualScene) -> list[float]:
        return [x + y for x, y in scene.edges_and_contours]


class ColorInformation(VisualInformation):
    info_type = "color"
    def _select_feature(self, scene: VisualScene) -> list[float]:
        return [scene.color_channels.get("red_green", 0.0),
                scene.color_channels.get("blue_yellow", 0.0),
                scene.color_channels.get("luminance", 0.0)]


class MotionInformation(VisualInformation):
    info_type = "motion"
    def _select_feature(self, scene: VisualScene) -> list[float]:
        return scene.frame_diff


class DepthInformation(VisualInformation):
    info_type = "depth"
    def _select_feature(self, scene: VisualScene) -> list[float]:
        return [scene.binocular_disparity] + scene.frame_diff[:3]


# =============================================================================
# F. MỞ RỘNG — thêm pathway mới không sửa Abstraction
# =============================================================================

class SuperiorColliculusPathway(Pathway):
    """
    Subcortical pathway — bypass cortex hoàn toàn.
    Cực nhanh (~10ms), low resolution, dùng cho reflex (vd: orienting eye
    về stimulus đột ngột). Bằng chứng: blindsight — bệnh nhân V1 hỏng vẫn
    có thể "đoán" vị trí stimulus dù không "thấy" (qua SC).
    """
    name = "superior_colliculus"

    def process(self, feature: list[float]) -> ProcessedSignal:
        # Cực nhanh, chỉ trả về "có" hoặc "không có" stimulus
        intensity = sum(abs(v) for v in feature) / max(len(feature), 1)
        return ProcessedSignal(
            spikes=[1.0 if intensity > 0.3 else 0.0], latency_ms=10,
            spatial_resolution="very_low", pathway_name=self.name,
        )


# =============================================================================
# G. ELLUMM — MemoryOperation × StorageBackend Bridge
# =============================================================================

class StorageBackend(ABC):
    """Implementor — backend lưu trữ."""
    @abstractmethod
    def put(self, key: str, value: dict) -> None: ...
    @abstractmethod
    def get(self, key: str) -> Optional[dict]: ...
    @abstractmethod
    def query(self, predicate) -> list[dict]: ...
    @property
    @abstractmethod
    def name(self) -> str: ...


class InMemoryDictStorage(StorageBackend):
    name = "in_memory_dict"
    def __init__(self):
        self._store: dict[str, dict] = {}
    def put(self, key, value): self._store[key] = value
    def get(self, key): return self._store.get(key)
    def query(self, predicate): return [v for v in self._store.values() if predicate(v)]


class SQLiteStorage(StorageBackend):
    """Mô phỏng — không thực sự dùng SQLite ở demo, chỉ minh họa swappable."""
    name = "sqlite"
    def __init__(self):
        self._table: list[tuple[str, dict]] = []
    def put(self, key, value): self._table.append((key, value))
    def get(self, key):
        for k, v in self._table:
            if k == key:
                return v
        return None
    def query(self, predicate): return [v for k, v in self._table if predicate(v)]


class VectorDBStorage(StorageBackend):
    """Mô phỏng — semantic search."""
    name = "vector_db"
    def __init__(self):
        self._vectors: dict[str, dict] = {}
    def put(self, key, value):
        # Giả lập embedding bằng tổng hash key
        emb = hash(key) % 1000
        self._vectors[key] = {**value, "_embedding": emb}
    def get(self, key): return self._vectors.get(key)
    def query(self, predicate): return [v for v in self._vectors.values() if predicate(v)]


# Abstraction
class MemoryOperation(ABC):
    """Abstraction — operation lưu trữ giữ ref tới StorageBackend."""

    def __init__(self, storage: StorageBackend):
        self._storage = storage

    @abstractmethod
    def execute(self, *args, **kwargs): ...

    @property
    def storage_name(self) -> str:
        return self._storage.name


class EncodeOperation(MemoryOperation):
    def execute(self, episode_id: str, episode: dict) -> str:
        # Logic riêng của Encode: validate trước khi store
        if "salience" not in episode:
            raise ValueError("Episode cần salience score")
        episode_with_meta = {**episode, "_op": "encode"}
        self._storage.put(episode_id, episode_with_meta)
        return f"Encoded '{episode_id}' to {self._storage.name}"


class RetrieveOperation(MemoryOperation):
    def execute(self, episode_id: str) -> Optional[dict]:
        result = self._storage.get(episode_id)
        if result:
            return {**result, "_retrieved_from": self._storage.name}
        return None


class ConsolidateOperation(MemoryOperation):
    def execute(self, threshold: float = 0.7) -> int:
        # Tìm episode có salience cao + tag "consolidated"
        high_salience = self._storage.query(lambda v: v.get("salience", 0) >= threshold)
        for ep in high_salience:
            ep["_consolidated"] = True
        return len(high_salience)


# =============================================================================
# DEMO
# =============================================================================

def demo() -> None:
    # Tạo scene chung cho mọi demo visual
    scene = VisualScene(
        edges_and_contours=[(0.3, 0.7), (0.5, 0.4), (0.2, 0.9)],
        color_channels={"red_green": 0.6, "blue_yellow": 0.3, "luminance": 0.8},
        frame_diff=[0.0, 0.1, 0.4, 0.8, 0.6, 0.2],
        binocular_disparity=0.05,
    )

    print("=" * 64)
    print("C. BRIDGE — runtime composition signal × pathway")
    print("=" * 64)
    # Cấu hình "sinh học chuẩn"
    form_p = FormInformation(ParvocellularPathway())
    color_p = ColorInformation(ParvocellularPathway())   # red-green qua P
    color_k = ColorInformation(KoniocellularPathway())   # blue-yellow qua K
    motion_m = MotionInformation(MagnocellularPathway())
    depth_m = DepthInformation(MagnocellularPathway())   # depth coarse qua M

    for info in [form_p, color_p, color_k, motion_m, depth_m]:
        result = info.extract(scene)
        print(f"  {info.info_type:8s} via {result.pathway_name:14s} → "
              f"latency={result.latency_ms}ms, resolution={result.spatial_resolution}, "
              f"spikes={[round(s, 2) for s in result.spikes[:3]]}...")

    print()
    print("=" * 64)
    print("D. RUNTIME SWAP — đổi pathway của motion (attentional re-routing)")
    print("=" * 64)
    print(f"  Trước: {motion_m.extract(scene).pathway_name}, "
          f"latency={motion_m.extract(scene).latency_ms}ms")
    motion_m.set_pathway(ParvocellularPathway())
    print(f"  Sau: {motion_m.extract(scene).pathway_name}, "
          f"latency={motion_m.extract(scene).latency_ms}ms")
    print("  → Sinh học: ít gặp, nhưng có trong attentional control khi cần")
    print("    high-resolution cho slow motion (vd: theo dõi chữ chạy chậm).")

    print()
    print("=" * 64)
    print("E. ACHROMATOPSIA — phá P-pathway destination cho color (V4)")
    print("=" * 64)

    class BrokenParvocellular(Pathway):
        """Mô phỏng V4 lesion — không xử lý được color."""
        name = "parvocellular_BROKEN"
        def process(self, feature):
            return ProcessedSignal([], 0, "none", self.name)

    color_broken = ColorInformation(BrokenParvocellular())
    form_broken = FormInformation(BrokenParvocellular())  # form qua P cũng bị nếu broken
    motion_intact = MotionInformation(MagnocellularPathway())  # motion qua M intact!

    print(f"  Color via broken P: spikes = {color_broken.extract(scene).spikes}")
    print(f"  Form  via broken P: spikes = {form_broken.extract(scene).spikes}")
    print(f"  Motion via intact M: spikes = "
          f"{[round(s, 2) for s in motion_intact.extract(scene).spikes]}")
    print("  → Color/form mất nhưng motion còn nguyên. Decoupling thực sự.")
    print("    Bằng chứng sinh học: bệnh nhân V4 lesion thấy 'phim đen trắng'")
    print("    nhưng vẫn theo dõi được chuyển động.")

    print()
    print("=" * 64)
    print("E2. AKINETOPSIA — phá M-pathway destination cho motion (V5/MT)")
    print("=" * 64)

    class BrokenMagnocellular(Pathway):
        name = "magnocellular_BROKEN"
        def process(self, feature):
            return ProcessedSignal([], 0, "none", self.name)

    form_intact = FormInformation(ParvocellularPathway())
    color_intact = ColorInformation(KoniocellularPathway())
    motion_broken = MotionInformation(BrokenMagnocellular())

    print(f"  Motion via broken M: spikes = {motion_broken.extract(scene).spikes}")
    print(f"  Form via intact P: spikes = "
          f"{[round(s, 2) for s in form_intact.extract(scene).spikes]}")
    print(f"  Color via intact K: spikes = "
          f"{[round(s, 2) for s in color_intact.extract(scene).spikes]}")
    print("  → Motion mất, form/color còn. Patient LM (1983) — không rót được")
    print("    nước vào cốc vì không thấy mức nước dâng.")

    print()
    print("=" * 64)
    print("F. MỞ RỘNG — thêm SuperiorColliculusPathway không sửa Abstraction")
    print("=" * 64)
    motion_sc = MotionInformation(SuperiorColliculusPathway())
    result = motion_sc.extract(scene)
    print(f"  Motion via SC: latency={result.latency_ms}ms, "
          f"resolution={result.spatial_resolution}, spikes={result.spikes}")
    print("  → Cực nhanh, dùng cho reflex orienting. SC bypass cortex.")
    print("  ✓ KHÔNG sửa class VisualInformation hay subclass nào.")

    print()
    print("=" * 64)
    print("G. ELLUMM — MemoryOperation × StorageBackend Bridge")
    print("=" * 64)

    # Tạo backend
    in_mem = InMemoryDictStorage()
    sqlite = SQLiteStorage()
    vector = VectorDBStorage()

    # Compose operation × backend
    print("\n  Encode 3 episode vào 3 backend khác nhau:")
    encode_im = EncodeOperation(in_mem)
    encode_sl = EncodeOperation(sqlite)
    encode_vd = EncodeOperation(vector)

    print("    " + encode_im.execute("ep_001", {"content": "saw apple", "salience": 0.6}))
    print("    " + encode_sl.execute("ep_002", {"content": "heard bell", "salience": 0.85}))
    print("    " + encode_vd.execute("ep_003", {"content": "felt wind", "salience": 0.4}))

    # Cùng RetrieveOperation, đổi backend runtime
    print("\n  Retrieve cùng episode_id qua 3 backend:")
    for backend in [in_mem, sqlite, vector]:
        retriever = RetrieveOperation(backend)
        # Thử retrieve ep_001 (chỉ có ở in_mem) và ep_002 (chỉ có ở sqlite)
        for ep_id in ["ep_001", "ep_002"]:
            r = retriever.execute(ep_id)
            print(f"    {ep_id} via {backend.name:18s}: "
                  f"{'found' if r else 'not found'}")

    # Consolidate operation chạy được trên mọi backend
    print("\n  Consolidate (salience >= 0.7) trên SQLite:")
    consolidate = ConsolidateOperation(sqlite)
    n = consolidate.execute(threshold=0.7)
    print(f"    Đã consolidate {n} episode")

    print()
    print("=" * 64)
    print("MỞ RỘNG ELLUMM — thêm BatchEncodeOperation, không sửa Storage")
    print("=" * 64)

    class BatchEncodeOperation(MemoryOperation):
        """Operation mới — encode batch episode trong một call."""
        def execute(self, episodes: dict[str, dict]) -> int:
            count = 0
            for ep_id, ep in episodes.items():
                if "salience" not in ep:
                    continue
                self._storage.put(ep_id, {**ep, "_op": "batch_encode"})
                count += 1
            return count

    batch = BatchEncodeOperation(in_mem)
    n = batch.execute({
        "ep_004": {"content": "wave", "salience": 0.5},
        "ep_005": {"content": "smile", "salience": 0.9},
        "ep_006": {"content": "no_salience"},   # bị skip
    })
    print(f"  Batch encoded {n}/3 episode (1 bị skip do thiếu salience)")
    print("  ✓ KHÔNG sửa StorageBackend hay backend nào — Open-Closed.")


if __name__ == "__main__":
    demo()


# =============================================================================
# THẢO LUẬN
# =============================================================================
#
# BRIDGE vs ADAPTER — phân biệt cuối cùng
# ────────────────────────────────────────
# - Adapter: cứu cánh khi 2 interface đã tồn tại không tương thích.
#            Quyết định MUỘN, sau khi đã có code.
# - Bridge:  thiết kế chủ động khi dự đoán 2 dimension độc lập sẽ mở rộng.
#            Quyết định SỚM, lúc design.
#
# Có thể combine: Bridge + Adapter
#    class CloudSyncStorage(StorageBackend):     ← Implementor mới
#        def __init__(self, s3_client):
#            self._adapter = S3ToStorageAdapter(s3_client)   ← Adapter bên trong
#        ...
# StorageBackend là Bridge interface; Adapter wrap S3 SDK bên dưới.
#
# BRIDGE vs STRATEGY
# ────────────────────
# Cả hai đều dùng composition + 1 hierarchy.
# Khác biệt:
# - Strategy: 1 abstraction, nhiều algorithm. Abstraction không có hierarchy
#             riêng (chỉ là client). Implementor = các algorithm.
# - Bridge:   Cả 2 phía đều có hierarchy. Abstraction là chính nó hierarchy
#             (RefinedAbstraction subclass), KHÔNG chỉ là client thụ động.
#
# Dấu hiệu nhận biết: nếu Abstraction của bạn có nhiều subclass (Refined),
# đó là Bridge. Nếu chỉ là 1 class dùng nhiều algorithm, đó là Strategy.
#
# KHI BRIDGE LÀ OVER-ENGINEERING
# ───────────────────────────────
# - Chỉ có 1 dimension thay đổi → dùng Strategy/Template Method.
# - 2 dimension nhưng 1 quá ổn định, gần như không bao giờ thay đổi →
#   inheritance đơn giản đủ, Bridge thêm complexity vô ích.
# - Domain quá nhỏ (≤ 3 class tổng cộng) → bridge không bù được abstraction overhead.
#
# Architect rule: nếu bạn không thể nêu được TÊN CỤ THỂ của ít nhất 2 biến thể
# trong mỗi dimension, đừng dùng Bridge — over-engineering.
"""
"""
