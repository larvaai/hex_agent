# -*- coding: utf-8 -*-
"""
Lesson 10 — Facade Pattern
Ví dụ neuroscience: brainstem là Facade vĩ đại — che hàng chục nucleus tự
động phức tạp (NTS, nucleus ambiguus, pre-Bötzinger, RVLM, ...) phía sau
interface đơn giản mà cortex có thể "nói": tăng nhịp thở, giảm arousal,
respond to stress.

File này triển khai 8 phần:
    A. ANTI-PATTERN — cortex client phải gọi 6 nucleus trực tiếp
    B. 8 subsystem class (nuclei brainstem) với state riêng
    C. BrainstemFacade với 6 high-level method
    D. Cortex client chỉ tương tác với Facade
    E. Demo subsystem swap (V1 → V2) không sửa client
    F. Demo brainstem stroke (phá Facade)
    G. Demo locked-in syndrome (đường dây cortex→Facade bị cắt)
    H. Ellumm: EllummCore Facade với 4 subsystem
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# =============================================================================
# B. SUBSYSTEM CLASSES — các nucleus của brainstem
# =============================================================================
# Mỗi class có state riêng và logic execution. Bình thường client KHÔNG nên
# gọi trực tiếp — phải qua Facade.

class PreBotzingerComplex:
    """Pacemaker chính cho inspiration."""
    def __init__(self):
        self.pace_rate: float = 12.0    # breaths per minute, baseline
        self.burst_pattern: str = "regular"

    def set_pace(self, target_rate: float) -> None:
        self.pace_rate = max(6.0, min(45.0, target_rate))

    def set_burst_pattern(self, pattern: str) -> None:
        self.burst_pattern = pattern    # "regular", "sigh", "gasp"

    def state(self) -> dict:
        return {"pace_rate": self.pace_rate, "burst_pattern": self.burst_pattern}


class BotzingerComplex:
    """Coordinate expiration phase."""
    def __init__(self):
        self.expiration_strength: float = 0.3

    def coordinate_expiration(self, breathing_rate: float) -> None:
        # Nhịp thở nhanh → cần expiration mạnh hơn
        self.expiration_strength = 0.3 + (breathing_rate - 12) * 0.02

    def state(self) -> dict:
        return {"expiration_strength": self.expiration_strength}


class ParafacialRespiratoryGroup:
    """Active expiration — chỉ active khi thở mạnh."""
    def __init__(self):
        self.active: bool = False

    def activate_when_needed(self, breathing_rate: float, threshold: float = 25) -> None:
        self.active = breathing_rate > threshold

    def state(self) -> dict:
        return {"active": self.active}


class NucleusTractusSolitarius:
    """NTS — visceral afferent hub. Baroreflex, chemoreflex, taste."""
    def __init__(self):
        self.chemoreceptor_gain: float = 1.0
        self.baroreflex_active: bool = True

    def adjust_chemoreceptor_gain(self, gain: float) -> None:
        self.chemoreceptor_gain = max(0.0, min(2.0, gain))

    def suppress_baroreflex_temporarily(self) -> None:
        self.baroreflex_active = False

    def restore_baroreflex(self) -> None:
        self.baroreflex_active = True

    def state(self) -> dict:
        return {"chemo_gain": self.chemoreceptor_gain,
                "baroreflex": self.baroreflex_active}


class NucleusAmbiguus:
    """Vagal motor — heart rate, swallowing, larynx."""
    def __init__(self):
        self.parasympathetic_tone: float = 0.6   # baseline rest

    def reduce_parasympathetic_tone(self, amount: float) -> None:
        self.parasympathetic_tone = max(0.0, self.parasympathetic_tone - amount)

    def restore_parasympathetic_tone(self) -> None:
        self.parasympathetic_tone = 0.6

    def initiate_swallow(self) -> str:
        return "26 muscles coordinated through 3 phases (oral, pharyngeal, esophageal)"

    def state(self) -> dict:
        return {"parasymp_tone": self.parasympathetic_tone}


class RostralVentrolateralMedulla:
    """RVLM — sympathetic vasomotor output, BP control."""
    def __init__(self):
        self.sympathetic_outflow: float = 0.4

    def elevate_sympathetic_outflow(self, amount: float) -> None:
        self.sympathetic_outflow = min(1.0, self.sympathetic_outflow + amount)

    def restore(self) -> None:
        self.sympathetic_outflow = 0.4

    def state(self) -> dict:
        return {"sympathetic_outflow": self.sympathetic_outflow}


class LocusCoeruleus:
    """LC — norepinephrine arousal (đã gặp ở Lesson 01)."""
    def __init__(self):
        self.ne_level: float = 30.0

    def release_norepinephrine(self, target: float) -> None:
        self.ne_level = max(0.0, min(100.0, target))

    def state(self) -> dict:
        return {"ne_level": self.ne_level}


class RapheNuclei:
    """Serotonin — mood, sleep regulation."""
    def __init__(self):
        self.serotonin_pattern: str = "tonic"

    def shift_pattern(self, pattern: str) -> None:
        self.serotonin_pattern = pattern   # "tonic", "burst", "alert", "sleep"

    def state(self) -> dict:
        return {"serotonin_pattern": self.serotonin_pattern}


# =============================================================================
# A. ANTI-PATTERN — Cortex client phải gọi mọi nucleus trực tiếp
# =============================================================================

def cortex_increases_breathing_anti_pattern(
    pre_botz: PreBotzingerComplex, botz: BotzingerComplex,
    parafacial: ParafacialRespiratoryGroup, nts: NucleusTractusSolitarius,
    target_rate: float = 22.0,
):
    """❌ Cortex phải biết tên 4 nucleus + thứ tự + tham số phù hợp."""
    pre_botz.set_pace(target_rate)
    botz.coordinate_expiration(target_rate)
    parafacial.activate_when_needed(target_rate, threshold=25)
    nts.adjust_chemoreceptor_gain(0.7)
    # Sửa subsystem (vd: thêm class mới) = phá mọi nơi gọi


# =============================================================================
# C. FACADE
# =============================================================================

class BrainstemFacade:
    """
    Facade vĩ đại — che 8+ nucleus phía sau 6 method cấp cao.
    """

    def __init__(self):
        self._pre_botz = PreBotzingerComplex()
        self._botz = BotzingerComplex()
        self._parafacial = ParafacialRespiratoryGroup()
        self._nts = NucleusTractusSolitarius()
        self._ambiguus = NucleusAmbiguus()
        self._rvlm = RostralVentrolateralMedulla()
        self._lc = LocusCoeruleus()
        self._raphe = RapheNuclei()

    # --- 6 high-level methods cho cortex ---

    def increase_breathing_rate(self, target_rate: float) -> dict:
        """Tăng nhịp thở. Bên trong orchestrate 4 nucleus."""
        self._pre_botz.set_pace(target_rate)
        self._botz.coordinate_expiration(target_rate)
        self._parafacial.activate_when_needed(target_rate)
        self._nts.adjust_chemoreceptor_gain(0.7)
        return self.respiratory_state()

    def arousal_up(self, strength: float = 0.5) -> dict:
        """Tăng arousal. Orchestrate LC + Raphe."""
        target_ne = 30.0 + strength * 60.0
        self._lc.release_norepinephrine(target=target_ne)
        self._raphe.shift_pattern("alert")
        return self.arousal_state()

    def relax(self) -> dict:
        """Trở về trạng thái nghỉ. Phục hồi mọi nucleus."""
        self._lc.release_norepinephrine(30.0)
        self._raphe.shift_pattern("tonic")
        self._ambiguus.restore_parasympathetic_tone()
        self._rvlm.restore()
        self._nts.restore_baroreflex()
        self._pre_botz.set_pace(12.0)
        return self.full_state()

    def respond_to_stress(self, intensity: float = 0.5) -> dict:
        """Fight-or-flight. 6 nucleus phải phối hợp."""
        self._lc.release_norepinephrine(target=70.0 + intensity * 25)
        self._rvlm.elevate_sympathetic_outflow(intensity)
        self._ambiguus.reduce_parasympathetic_tone(intensity * 0.6)
        self._nts.suppress_baroreflex_temporarily()
        self._pre_botz.set_pace(12.0 + intensity * 10)
        self._raphe.shift_pattern("alert")
        return self.full_state()

    def initiate_swallow(self) -> str:
        """Cortex chỉ cần 'tôi muốn nuốt'."""
        return self._ambiguus.initiate_swallow()

    def emergency_apnea_stop(self, duration_sec: float = 5.0) -> str:
        """Voluntary breath hold — cortex override với giới hạn."""
        # Brainstem có 'veto power' — không cho phép > 90 giây
        if duration_sec > 90.0:
            return "REJECTED: brainstem won't allow apnea > 90s (vital function protection)"
        return f"Holding breath for {duration_sec}s (cortex override)"

    # --- State queries ---

    def respiratory_state(self) -> dict:
        return {
            "pre_botzinger": self._pre_botz.state(),
            "botzinger": self._botz.state(),
            "parafacial": self._parafacial.state(),
            "nts_chemo": self._nts.chemoreceptor_gain,
        }

    def arousal_state(self) -> dict:
        return {
            "locus_coeruleus": self._lc.state(),
            "raphe": self._raphe.state(),
        }

    def full_state(self) -> dict:
        return {
            **self.respiratory_state(),
            **self.arousal_state(),
            "ambiguus": self._ambiguus.state(),
            "rvlm": self._rvlm.state(),
            "nts": self._nts.state(),
        }


# =============================================================================
# D. CORTEX CLIENT — chỉ biết Facade
# =============================================================================

class CortexClient:
    """High-level decision making. KHÔNG import nucleus nào."""

    def __init__(self, brainstem: BrainstemFacade):
        self.brainstem = brainstem

    def decide_to_run(self) -> None:
        print("  Cortex: 'Tôi đang chạy bộ' →")
        self.brainstem.increase_breathing_rate(target_rate=22.0)
        self.brainstem.arousal_up(strength=0.4)

    def decide_to_sleep(self) -> None:
        print("  Cortex: 'Tôi muốn ngủ' →")
        self.brainstem.relax()
        self.brainstem._raphe.shift_pattern("sleep")    # advanced: bypass Facade

    def encounter_threat(self, intensity: float) -> None:
        print(f"  Cortex: 'Có nguy hiểm! intensity={intensity}' →")
        self.brainstem.respond_to_stress(intensity)

    def want_to_swallow(self) -> str:
        print("  Cortex: 'Nuốt' →")
        return self.brainstem.initiate_swallow()


# =============================================================================
# H. ELLUMM — EllummCore Facade
# =============================================================================
# 4 subsystem internal, mỗi cái có nhiều class. Facade expose 4 method.

class _MemorySubsystem:
    """Subsystem nội bộ — encoder + storage + retriever + consolidator."""
    def __init__(self):
        self._store: dict[str, dict] = {}
        self._index: dict[str, list[str]] = {}   # tag → episode_ids

    def encode(self, episode_id: str, episode: dict) -> None:
        self._store[episode_id] = {**episode, "consolidated": False}
        for tag in episode.get("tags", []):
            self._index.setdefault(tag, []).append(episode_id)

    def retrieve(self, query: str) -> list[dict]:
        results = []
        q = query.lower()
        for tag, ids in self._index.items():
            if q in tag.lower():
                for ep_id in ids:
                    results.append({"id": ep_id, **self._store[ep_id]})
        return results

    def consolidate_high_salience(self, threshold: float = 0.7) -> int:
        n = 0
        for ep_id, ep in self._store.items():
            if ep.get("salience", 0) >= threshold:
                ep["consolidated"] = True
                n += 1
        return n


class _EmotionSubsystem:
    def __init__(self):
        self.arousal: float = 30.0
        self.valence: float = 0.0
        self.cortisol: float = 5.0

    def tag_episode(self, episode: dict) -> dict:
        salience = episode.get("salience", 0.5)
        episode["emotion_tag"] = {
            "arousal_at_encode": self.arousal,
            "valence_at_encode": self.valence,
            "cortisol_at_encode": self.cortisol,
        }
        # Salience cao → arousal tự tăng
        self.arousal = min(95.0, self.arousal + salience * 20)
        return episode

    def relax(self) -> None:
        self.arousal = 30.0
        self.cortisol = 5.0


class _AttentionSubsystem:
    def __init__(self):
        self.bottom_up_priority: float = 0.5

    def assess_salience(self, stimulus: dict) -> float:
        # Salience = kết hợp novelty + emotional weight
        novelty = stimulus.get("novelty", 0.5)
        emotional_weight = abs(stimulus.get("valence_hint", 0))
        return min(1.0, 0.4 * novelty + 0.6 * emotional_weight)


class _LearningSubsystem:
    def __init__(self):
        self.weight_updates: int = 0

    def maybe_update(self, episode: dict, threshold: float = 0.5) -> bool:
        salience = episode.get("salience", 0)
        if salience >= threshold:
            self.weight_updates += 1
            return True
        return False


class EllummCore:
    """Facade duy nhất cho toàn bộ Ellumm engine."""

    def __init__(self):
        self._memory = _MemorySubsystem()
        self._emotion = _EmotionSubsystem()
        self._attention = _AttentionSubsystem()
        self._learning = _LearningSubsystem()
        self._counter = 0

    def process_stimulus(self, stimulus: dict) -> dict:
        """Single API call → 4 subsystem orchestrate."""
        # 1. Attention assess
        salience = self._attention.assess_salience(stimulus)
        # 2. Quyết định encode
        if salience < 0.3:
            return {"encoded": False, "reason": "low_salience", "salience": salience}
        # 3. Build episode
        self._counter += 1
        ep_id = f"ep_{self._counter:04d}"
        episode = {
            "content": stimulus.get("content", "(unknown)"),
            "salience": salience,
            "tags": stimulus.get("tags", []),
        }
        # 4. Tag với emotion
        episode = self._emotion.tag_episode(episode)
        # 5. Memory encode
        self._memory.encode(ep_id, episode)
        # 6. Learning maybe update
        learned = self._learning.maybe_update(episode)
        return {"encoded": True, "id": ep_id, "salience": salience, "learned": learned}

    def recall(self, query: str) -> list[dict]:
        return self._memory.retrieve(query)

    def dream(self) -> dict:
        """Consolidation cycle — gọi đúng thứ tự subsystem."""
        n_consolidated = self._memory.consolidate_high_salience(0.7)
        self._emotion.relax()
        return {"consolidated": n_consolidated, "arousal_after": self._emotion.arousal}

    def report_state(self) -> dict:
        return {
            "n_episodes": len(self._memory._store),
            "arousal": self._emotion.arousal,
            "valence": self._emotion.valence,
            "cortisol": self._emotion.cortisol,
            "weight_updates": self._learning.weight_updates,
        }


# =============================================================================
# DEMO
# =============================================================================

def demo() -> None:
    print("=" * 64)
    print("D. CORTEX CLIENT QUA FACADE — không thấy nucleus nào")
    print("=" * 64)
    brainstem = BrainstemFacade()
    cortex = CortexClient(brainstem)

    cortex.decide_to_run()
    print(f"    Resp state: {brainstem.respiratory_state()}")
    print(f"    Arousal: NE = {brainstem._lc.ne_level}")

    cortex.encounter_threat(intensity=0.7)
    print(f"    Full state after stress:")
    for k, v in brainstem.full_state().items():
        print(f"      {k}: {v}")

    print(f"\n    Swallow result: {cortex.want_to_swallow()}")

    print(f"\n    Voluntary breath hold (10s): {brainstem.emergency_apnea_stop(10)}")
    print(f"    Voluntary breath hold (120s): {brainstem.emergency_apnea_stop(120)}")
    print("    → Brainstem có veto power — protect vital function.")

    cortex.decide_to_sleep()
    print(f"    State after sleep decision: arousal={brainstem._lc.ne_level}, "
          f"raphe={brainstem._raphe.serotonin_pattern}")

    print()
    print("=" * 64)
    print("E. SUBSYSTEM SWAP — V1 → V2 không sửa client")
    print("=" * 64)

    # Phiên bản V2 của PreBötzinger với pacemaker burst pattern thông minh hơn
    class PreBotzingerComplexV2(PreBotzingerComplex):
        def set_pace(self, target_rate: float) -> None:
            super().set_pace(target_rate)
            # V2: tự động chọn burst pattern phù hợp
            if target_rate > 25:
                self.burst_pattern = "high_freq_short_burst"
            elif target_rate < 10:
                self.burst_pattern = "deep_slow_burst"
            else:
                self.burst_pattern = "regular"

    # Hot-swap implementation trong Facade
    brainstem._pre_botz = PreBotzingerComplexV2()
    cortex.decide_to_run()
    print(f"    V2 burst pattern at rate=22: '{brainstem._pre_botz.burst_pattern}'")
    print("    ✓ CortexClient không sửa dòng nào.")

    print()
    print("=" * 64)
    print("F. BRAINSTEM STROKE — phá Facade")
    print("=" * 64)

    class BrokenBrainstemFacade:
        """Stroke phá brainstem → mọi method raise."""
        def __getattr__(self, name):
            raise SystemError(f"Brainstem stroke: '{name}' không khả dụng")

    broken_brainstem = BrokenBrainstemFacade()
    broken_cortex = CortexClient(broken_brainstem)
    try:
        broken_cortex.decide_to_run()
    except SystemError as e:
        print(f"  ✗ {e}")
        print("  → Cortex còn nguyên ý thức nhưng không vận hành được vital functions.")
        print("    Lâm sàng: ngừng thở, BP sụp, HR rối loạn → tử vong nhanh.")

    print()
    print("=" * 64)
    print("G. LOCKED-IN SYNDROME — đường dây cortex→Facade bị cắt")
    print("=" * 64)

    class CortexWithSeveredPathway:
        def __init__(self, brainstem):
            self.brainstem = brainstem
            self._can_send_intent: bool = False    # ventral pons lesion

        def decide_to_run(self):
            print("  Cortex: 'Tôi muốn vận động' →")
            if not self._can_send_intent:
                print("    ✗ Không thể gửi intent xuống brainstem (corticospinal tract gãy)")
                print("    → Chỉ cử động được mắt (pathway riêng từ midbrain)")
                return
            self.brainstem.increase_breathing_rate(20)

    locked = CortexWithSeveredPathway(BrainstemFacade())
    locked.decide_to_run()
    print(f"  → Brainstem facade vẫn nguyên (vital functions OK), cortex tỉnh táo,")
    print(f"    nhưng client không thể call Facade vì 'connection' bị đứt.")

    print()
    print("=" * 64)
    print("H. ELLUMM — EllummCore Facade với 4 subsystem")
    print("=" * 64)
    core = EllummCore()

    # User chỉ thấy 4 method, không biết về 4 subsystem internal
    print("\n  process_stimulus 5 stimuli khác nhau:")
    stimuli = [
        {"content": "saw apple", "novelty": 0.3, "valence_hint": 0.2, "tags": ["apple", "fruit"]},
        {"content": "snake near garden!", "novelty": 0.9, "valence_hint": -0.95,
         "tags": ["snake", "fear", "garden"]},
        {"content": "background hum", "novelty": 0.1, "valence_hint": 0.0, "tags": ["bg_noise"]},
        {"content": "received gift", "novelty": 0.6, "valence_hint": 0.8, "tags": ["gift", "happy"]},
        {"content": "wall is white", "novelty": 0.05, "valence_hint": 0, "tags": ["wall"]},
    ]
    for s in stimuli:
        result = core.process_stimulus(s)
        marker = "✓" if result["encoded"] else "✗"
        print(f"    {marker} {s['content']}: salience={result['salience']:.2f}, "
              f"encoded={result['encoded']}, "
              f"learned={result.get('learned', '-')}")

    print("\n  recall('snake'):")
    snake_memos = core.recall("snake")
    for m in snake_memos:
        print(f"    - {m['id']}: '{m['content']}' (salience={m['salience']:.2f})")

    print(f"\n  state trước dream:")
    state_before = core.report_state()
    print(f"    {state_before}")

    print("\n  dream() — consolidation cycle:")
    dream_result = core.dream()
    print(f"    {dream_result}")

    print(f"\n  state sau dream: {core.report_state()}")
    print("  ✓ User chỉ gọi 4 method. Internal có 4 subsystem × ~3 class = 12 component.")


if __name__ == "__main__":
    demo()


# =============================================================================
# THẢO LUẬN
# =============================================================================
#
# FACADE vs ADAPTER (lesson 06)
# ─────────────────────────────
# - Adapter: 1 class A → 1 class B (translation)
# - Facade: nhiều class (subsystem) → 1 interface đơn giản (aggregation)
#
# FACADE vs MEDIATOR (lesson 17)
# ──────────────────────────────
# - Facade: 1 chiều (client → subsystem). Subsystem KHÔNG biết Facade.
# - Mediator: 2 chiều (peer ↔ peer qua mediator). Peers BIẾT mediator.
#
# Brainstem trong neuroscience thực ra mang cả 2 vai trò:
# - Facade cho cortex (cortex chỉ thấy interface đơn giản)
# - Mediator giữa các nucleus (NTS coordinate giữa baroreflex và breathing)
# Khi dạy, tách 2 role để client thấy rõ pattern khác nhau.
#
# DẤU HIỆU FACADE → GOD OBJECT
# ────────────────────────────
# - Facade > 500 dòng → tách thành nhiều Facade theo concern
# - > 15 subsystem dependency → có thể cần thêm 1 lớp trung gian
# - Mọi method đụng > 5 subsystem → subsystem cần refactor, không phải Facade
# - Test khó vì phải mock 30+ thứ → quá nhiều coupling
#
# Quy tắc: Facade tốt là Facade ngắn (<300 dòng), method ít (5-10), mỗi method
# orchestrate ≤ 5 subsystem call. Não brainstem có ~30 nucleus nhưng cortex
# chỉ "nói chuyện" qua < 10 channel cao cấp — đó là tỉ lệ design tốt.
#
# KHI KHÔNG NÊN DÙNG FACADE
# ─────────────────────────
# - Subsystem chỉ có 1-2 class → không cần Facade
# - Client luôn cần fine-grained control (vd: testing framework)
# - Tất cả client đều dùng subsystem theo cách khác nhau → Facade chỉ cản
"""
"""
