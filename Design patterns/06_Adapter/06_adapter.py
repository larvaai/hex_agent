"""
Lesson 06 — Adapter Pattern
Ví dụ neuroscience: thalamus = "the great relay station". Mỗi nucleus thalamic
adapt một loại signal raw từ periphery (retina/cochlea/skin) sang format
thalamocortical chuẩn mà cortex có thể đọc.

File này triển khai 7 phần:
    A. 3 ADAPTEE với interface raw không tương thích nhau (Retina, Cochlea, Skin)
    B. TARGET interface ThalamocorticalSignal
    C. 3 CONCRETE ADAPTER: LGNAdapter, MGNAdapter, VPLAdapter
    D. Cortex client phụ thuộc CHỈ vào Target interface
    E. Demo thalamic stroke (adapter mất → cortex mất modality)
    F. Two-way adapter: cortico-thalamo-cortical loop
    G. Ellumm: SensoryInputAdapter cho camera/mic/file/webhook
"""

from __future__ import annotations
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Any, Optional


# =============================================================================
# B. TARGET INTERFACE — cái cortex/Ellumm core kỳ vọng
# =============================================================================

@dataclass
class Spike:
    layer: int                  # 1..6 (cortical layer)
    intensity: float            # 0.0 - 1.0
    feature_index: int          # spatial/frequency/body-part index


@runtime_checkable
class ThalamocorticalSignal(Protocol):
    """
    Interface chuẩn mà cortex hiểu được.
    Mọi adapter phải implement đủ 3 method này.
    """
    def get_spikes(self) -> list[Spike]: ...
    def modality(self) -> str: ...
    def timestamp_ms(self) -> int: ...


# =============================================================================
# A. ADAPTEE — interface raw, không tương thích nhau
# =============================================================================

@dataclass
class RetinalBurst:
    """Output thô của retinal ganglion cell — KHÔNG phải spike chuẩn cortex."""
    on_center_cells: list[float]      # M-cell magnocellular response
    off_center_cells: list[float]     # P-cell parvocellular response
    eccentricity: float                # vị trí so với fovea


class Retina:
    """Adaptee — phát signal theo cách của retina, không biết gì về cortex."""
    def fire_ganglion_cells(self, scene_brightness: float) -> RetinalBurst:
        # Mô phỏng đơn giản: brightness → on-center burst pattern
        on = [scene_brightness * (1.0 - i * 0.1) for i in range(8)]
        off = [(1.0 - scene_brightness) * (1.0 - i * 0.1) for i in range(8)]
        return RetinalBurst(on_center_cells=on, off_center_cells=off, eccentricity=0.3)


@dataclass
class CochlearWaveform:
    """Output thô của cochlear nerve — tonotopic frequency response."""
    frequency_band_hz: list[tuple[float, float]]   # (freq, intensity)
    duration_ms: int


class Cochlea:
    """Adaptee — phát signal theo tonotopic map, không phải spike layer."""
    def basilar_membrane_response(self, sound: dict) -> CochlearWaveform:
        # Mô phỏng: sound dict → frequency bands
        freq_bands = [(440.0 * (2 ** i), sound.get("loudness", 0.5))
                      for i in range(-2, 3)]
        return CochlearWaveform(frequency_band_hz=freq_bands, duration_ms=100)


@dataclass
class SomatosensoryReading:
    """Output thô của skin/muscle afferent — body-part organized."""
    body_part: str
    pressure: float
    temperature_c: float
    proprioception_angle: Optional[float] = None


class Skin:
    """Adaptee — phát signal theo body-map, không phải spike layer."""
    def afferent_signal(self, stimulation: dict) -> SomatosensoryReading:
        return SomatosensoryReading(
            body_part=stimulation.get("part", "fingertip"),
            pressure=stimulation.get("pressure", 0.5),
            temperature_c=stimulation.get("temp", 32.0),
        )


# =============================================================================
# C. CONCRETE ADAPTERS — Object Adapter (composition)
# =============================================================================

class LGNAdapter:
    """
    Lateral Geniculate Nucleus — adapter cho visual.
    Chuyển RetinalBurst → list[Spike] với 6 layer thalamocortical chuẩn.
    """
    def __init__(self, retina: Retina, scene_brightness: float = 0.7):
        self._retina = retina
        self._scene = scene_brightness

    def get_spikes(self) -> list[Spike]:
        raw = self._retina.fire_ganglion_cells(self._scene)
        spikes: list[Spike] = []
        # Layer 1-4: parvocellular (P-cell, off-center)
        for idx, val in enumerate(raw.off_center_cells[:4]):
            spikes.append(Spike(layer=idx + 1, intensity=val, feature_index=idx))
        # Layer 5-6: magnocellular (M-cell, on-center)
        for idx, val in enumerate(raw.on_center_cells[:2]):
            spikes.append(Spike(layer=5 + idx, intensity=val, feature_index=idx))
        return spikes

    def modality(self) -> str:
        return "visual"

    def timestamp_ms(self) -> int:
        return int(time.time() * 1000)


class MGNAdapter:
    """
    Medial Geniculate Nucleus — adapter cho auditory.
    Chuyển CochlearWaveform → list[Spike] với layer organization theo frequency.
    """
    def __init__(self, cochlea: Cochlea, sound: dict):
        self._cochlea = cochlea
        self._sound = sound

    def get_spikes(self) -> list[Spike]:
        raw = self._cochlea.basilar_membrane_response(self._sound)
        spikes: list[Spike] = []
        # Mapping tonotopic: low freq → layer 1-2, high freq → layer 5-6
        for idx, (freq, intensity) in enumerate(raw.frequency_band_hz):
            layer = 1 + min(5, int((freq / 880.0)))
            spikes.append(Spike(layer=layer, intensity=intensity, feature_index=idx))
        return spikes

    def modality(self) -> str:
        return "auditory"

    def timestamp_ms(self) -> int:
        return int(time.time() * 1000)


class VPLAdapter:
    """
    Ventral Posterior Lateral nucleus — adapter cho somatosensory.
    Chuyển SomatosensoryReading → list[Spike] theo body-part topographic map.
    """
    BODY_PART_INDEX = {"fingertip": 0, "palm": 1, "forearm": 2, "shoulder": 3, "foot": 4}

    def __init__(self, skin: Skin, stimulation: dict):
        self._skin = skin
        self._stim = stimulation

    def get_spikes(self) -> list[Spike]:
        raw = self._skin.afferent_signal(self._stim)
        body_idx = self.BODY_PART_INDEX.get(raw.body_part, 5)
        # Pressure → layer 1-4 (lemniscal pathway)
        # Temperature → layer 5-6 (spinothalamic-like)
        return [
            Spike(layer=2, intensity=raw.pressure, feature_index=body_idx),
            Spike(layer=5, intensity=(raw.temperature_c - 25.0) / 15.0, feature_index=body_idx),
        ]

    def modality(self) -> str:
        return "somatosensory"

    def timestamp_ms(self) -> int:
        return int(time.time() * 1000)


# =============================================================================
# D. CLIENT — Cortex chỉ phụ thuộc Target interface
# =============================================================================

class Cortex:
    """
    Client. Không biết retina/cochlea/skin tồn tại.
    Chỉ thấy ThalamocorticalSignal (Target).
    """
    def __init__(self):
        self._inputs: list[ThalamocorticalSignal] = []

    def subscribe(self, signal: ThalamocorticalSignal) -> None:
        self._inputs.append(signal)

    def process_all(self) -> dict[str, list[Spike]]:
        """Xử lý mỗi modality, trả về dict modality → spikes."""
        result: dict[str, list[Spike]] = {}
        for src in self._inputs:
            spikes = src.get_spikes()
            mod = src.modality()
            result[mod] = spikes
        return result


# =============================================================================
# F. TWO-WAY ADAPTER — cortico-thalamo-cortical loop
# =============================================================================

class CorticothalamicFeedback:
    """
    Cortex thường gửi feedback về thalamus (gain modulation, attention).
    Adapter hai chiều: vừa adapt periphery → cortex, vừa nhận cortex feedback.
    """
    def __init__(self, lgn: LGNAdapter):
        self._lgn = lgn
        self._gain_modulation: float = 1.0

    def receive_attention_signal(self, attention_strength: float) -> None:
        """Cortex bảo thalamus 'tăng độ nhạy với input visual'."""
        self._gain_modulation = 1.0 + attention_strength

    def get_modulated_spikes(self) -> list[Spike]:
        spikes = self._lgn.get_spikes()
        # Áp gain modulation lên mọi spike
        return [Spike(layer=s.layer, intensity=s.intensity * self._gain_modulation,
                      feature_index=s.feature_index)
                for s in spikes]


# =============================================================================
# G. ELLUMM — SensoryInputAdapter
# =============================================================================

@dataclass
class SensoryInput:
    modality: str
    timestamp_ns: int
    payload: bytes
    metadata: dict = field(default_factory=dict)
    confidence: float = 1.0


@runtime_checkable
class SensoryInputProtocol(Protocol):
    def read(self) -> SensoryInput: ...


# Adaptee 1: giả lập OpenCV camera
class FakeCV2VideoCapture:
    def __init__(self, width: int = 640, height: int = 480):
        self._w, self._h = width, height
        self._frame_count = 0

    def read(self) -> tuple[bool, bytes]:
        self._frame_count += 1
        # Mô phỏng RGB ndarray.tobytes() — ở đây dùng dummy
        fake_frame = bytes([self._frame_count % 256]) * (self._w * self._h * 3)
        return True, fake_frame


# Adapter 1
class CameraAdapter:
    def __init__(self, cv2_capture: FakeCV2VideoCapture):
        self._cap = cv2_capture

    def read(self) -> SensoryInput:
        ok, frame = self._cap.read()
        return SensoryInput(
            modality="visual",
            timestamp_ns=time.time_ns(),
            payload=frame,
            metadata={"width": self._cap._w, "height": self._cap._h, "format": "BGR"},
            confidence=1.0 if ok else 0.0,
        )


# Adaptee 2: giả lập PortAudio
class FakePortAudioStream:
    def __init__(self, sample_rate: int = 44100):
        self._sr = sample_rate

    def read(self, n_frames: int) -> bytes:
        # Mô phỏng PCM int16 little-endian
        return (b"\x00\x10") * n_frames


# Adapter 2
class MicAdapter:
    def __init__(self, stream: FakePortAudioStream, n_frames: int = 1024):
        self._stream = stream
        self._n = n_frames

    def read(self) -> SensoryInput:
        pcm = self._stream.read(self._n)
        return SensoryInput(
            modality="auditory",
            timestamp_ns=time.time_ns(),
            payload=pcm,
            metadata={"sample_rate": self._stream._sr, "format": "PCM_S16LE", "n_frames": self._n},
            confidence=1.0,
        )


# Adaptee 3: file system event
@dataclass
class InotifyEvent:
    path: str
    event_type: str   # 'create', 'modify', 'delete'


class FakeInotifyWatcher:
    def __init__(self, events: list[InotifyEvent]):
        self._events = events
        self._idx = 0

    def next_event(self) -> Optional[InotifyEvent]:
        if self._idx >= len(self._events):
            return None
        e = self._events[self._idx]
        self._idx += 1
        return e


# Adapter 3
class FileEventAdapter:
    def __init__(self, watcher: FakeInotifyWatcher):
        self._w = watcher

    def read(self) -> SensoryInput:
        ev = self._w.next_event()
        if ev is None:
            return SensoryInput(
                modality="system_event", timestamp_ns=time.time_ns(),
                payload=b"", metadata={"empty": True}, confidence=0.0,
            )
        return SensoryInput(
            modality="system_event",
            timestamp_ns=time.time_ns(),
            payload=ev.path.encode("utf-8"),
            metadata={"event_type": ev.event_type, "source": "filesystem"},
            confidence=1.0,
        )


# =============================================================================
# DEMO
# =============================================================================

def demo() -> None:
    print("=" * 64)
    print("D. CORTEX CLIENT — chỉ phụ thuộc Target interface")
    print("=" * 64)
    cortex = Cortex()
    # Setup các adapter
    cortex.subscribe(LGNAdapter(Retina(), scene_brightness=0.8))
    cortex.subscribe(MGNAdapter(Cochlea(), sound={"loudness": 0.6}))
    cortex.subscribe(VPLAdapter(Skin(), stimulation={"part": "fingertip", "pressure": 0.4, "temp": 36.5}))

    result = cortex.process_all()
    for modality, spikes in result.items():
        print(f"\n  Modality: {modality} ({len(spikes)} spikes)")
        for sp in spikes:
            print(f"    layer={sp.layer}, intensity={sp.intensity:.2f}, "
                  f"feature_idx={sp.feature_index}")

    print()
    print("=" * 64)
    print("E. THALAMIC STROKE — LGN bị tổn thương")
    print("=" * 64)
    cortex2 = Cortex()
    cortex2.subscribe(MGNAdapter(Cochlea(), sound={"loudness": 0.7}))
    cortex2.subscribe(VPLAdapter(Skin(), stimulation={"part": "palm", "pressure": 0.6, "temp": 35.0}))
    # KHÔNG subscribe LGN — mô phỏng LGN stroke
    result2 = cortex2.process_all()
    print(f"  Modality nhận được: {list(result2.keys())}")
    print("  ⚠ Visual modality không có — cortical blindness mặc dù retina + V1 còn nguyên.")
    print("  → Sinh học: tổn thương thalamus đứt 'cây cầu' giữa periphery và cortex.")

    print()
    print("=" * 64)
    print("F. TWO-WAY ADAPTER — cortico-thalamo-cortical loop")
    print("=" * 64)
    lgn = LGNAdapter(Retina(), scene_brightness=0.5)
    feedback = CorticothalamicFeedback(lgn)

    print("  Trước attention modulation:")
    for sp in feedback.get_modulated_spikes()[:3]:
        print(f"    layer={sp.layer}, intensity={sp.intensity:.3f}")

    feedback.receive_attention_signal(0.5)   # Cortex nói "chú ý visual!"
    print("\n  Sau attention modulation (gain x1.5):")
    for sp in feedback.get_modulated_spikes()[:3]:
        print(f"    layer={sp.layer}, intensity={sp.intensity:.3f}")

    print()
    print("=" * 64)
    print("G. ELLUMM — SensoryInputAdapter cho 3 nguồn khác nhau")
    print("=" * 64)
    adapters: list[SensoryInputProtocol] = [
        CameraAdapter(FakeCV2VideoCapture(width=320, height=240)),
        MicAdapter(FakePortAudioStream(sample_rate=22050), n_frames=512),
        FileEventAdapter(FakeInotifyWatcher([
            InotifyEvent("/data/notes/today.md", "create"),
            InotifyEvent("/data/notes/today.md", "modify"),
        ])),
    ]

    print("\n  Engine xử lý mọi adapter qua interface chuẩn:")
    for adapter in adapters:
        for _ in range(2):       # đọc 2 lần mỗi nguồn
            inp = adapter.read()
            payload_preview = inp.payload[:8].hex() if inp.payload else "(empty)"
            print(f"    [{inp.modality}] ts={inp.timestamp_ns}, "
                  f"meta={inp.metadata}, payload[:8]={payload_preview}")

    print()
    print("=" * 64)
    print("MỞ RỘNG: thêm modality mới (vestibular) — không sửa cortex")
    print("=" * 64)

    # Adaptee mới
    class VestibularSystem:
        def head_orientation(self) -> dict:
            return {"pitch": 5.2, "yaw": -1.3, "roll": 0.5}

    # Adapter mới
    class VLAdapter:
        """Adapter cho vestibular nucleus (VL = ventral lateral, đơn giản hóa)."""
        def __init__(self, vest: VestibularSystem):
            self._v = vest

        def get_spikes(self) -> list[Spike]:
            o = self._v.head_orientation()
            return [
                Spike(layer=3, intensity=abs(o["pitch"]) / 10.0, feature_index=0),
                Spike(layer=3, intensity=abs(o["yaw"]) / 10.0, feature_index=1),
                Spike(layer=3, intensity=abs(o["roll"]) / 10.0, feature_index=2),
            ]
        def modality(self) -> str: return "vestibular"
        def timestamp_ms(self) -> int: return int(time.time() * 1000)

    # Cortex hoàn toàn không bị sửa — chỉ subscribe thêm
    cortex.subscribe(VLAdapter(VestibularSystem()))
    new_result = cortex.process_all()
    print(f"  Modality sau khi thêm vestibular: {list(new_result.keys())}")
    print("  ✓ Cortex không sửa dòng nào — Open-Closed về phía thêm modality.")


if __name__ == "__main__":
    demo()


# =============================================================================
# THẢO LUẬN
# =============================================================================
#
# OBJECT ADAPTER vs CLASS ADAPTER trong Python
# ─────────────────────────────────────────────
# Object adapter (dùng composition): linh hoạt, có thể đổi adaptee runtime,
# có thể có 1 adapter wrap nhiều adaptee. ĐÂY LÀ DEFAULT trong Python.
#
# Class adapter (multiple inheritance): cứng nhắc hơn, có thể override
# method của adaptee. Trong Python ít dùng vì:
#   - MRO (Method Resolution Order) phức tạp với multi-inheritance
#   - Diamond problem dễ xảy ra
#   - Composition rõ ràng hơn cho người đọc
#
# DẤU HIỆU ADAPTER ĐANG TRỞ THÀNH PATTERN KHÁC
# ─────────────────────────────────────────────
# - Adapter có > 50 dòng logic xử lý → đã trở thành Decorator (lesson 09)
#   nếu thêm hành vi, hoặc Facade (lesson 10) nếu đơn giản hóa subsystem.
# - Adapter có state riêng phức tạp → có thể đã thành Proxy (lesson 12)
#   nếu kiểm soát truy cập.
# - Adapter chọn giữa nhiều adaptee runtime → Strategy (lesson 21).
#
# Adapter ĐÚNG khi: chỉ làm format/interface translation, không thêm logic.
#
# ANTI-CORRUPTION LAYER (DDD)
# ────────────────────────────
# Trong Domain-Driven Design, Adapter là pattern chủ lực để bảo vệ domain
# khỏi external bounded context. Khi tích hợp với:
#   - Legacy system → Adapter
#   - Third-party API → Adapter
#   - External data format (XML, ProtoBuf, etc.) → Adapter
# Domain code chỉ thấy clean domain interface, mọi "rác" external nằm
# bên kia adapter. Khi vendor đổi API, chỉ sửa adapter.
"""
"""
