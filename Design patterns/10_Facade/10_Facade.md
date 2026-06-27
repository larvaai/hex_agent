# Lesson 10 — Facade

> **Cung cấp một interface đơn giản phía trước một subsystem phức tạp, để client không phải biết chi tiết bên trong.**

---

## Mức 1 — CONCEPT (Ý tưởng)

### Vấn đề pattern giải quyết

Bạn có một subsystem với 10–30 class internal phối hợp với nhau theo cách phức tạp. Client cần "hoàn thành 1 tác vụ" mức cao — nhưng để làm được, ngây thơ ra phải hiểu hết:

```python
# ❌ Client phải biết toàn bộ subsystem nội bộ
def cortex_initiates_breathing_increase():
    pre_botzinger = PreBotzingerComplex()
    botzinger = BotzingerComplex()
    nts = NucleusTractusSolitarius()
    rvlm = RostralVentrolateralMedulla()
    ambig = NucleusAmbiguus()
    parafacial = ParafacialRespiratoryGroup()

    # Phải biết thứ tự, dependency, side effect
    pre_botzinger.set_pace(target_rate=20)
    botzinger.coordinate_expiration(rate=20)
    parafacial.modulate_active_expiration(strength=0.6)
    nts.adjust_chemoreceptor_gain(0.7)
    rvlm.elevate_sympathetic_outflow(0.5)
    ambig.reduce_parasympathetic_tone(0.4)

    # Mỗi project, mỗi developer phải lặp lại logic này
    # Sửa subsystem = sửa mọi client
```

Coupling kinh khủng:
- Client biết tên 6 nucleus.
- Client biết thứ tự setup.
- Client biết tham số phù hợp.
- Sửa subsystem (vd: thêm Bötzinger nucleus mới, thay pre-Bötzinger algorithm) = phá mọi nơi gọi.

Facade giải quyết bằng cách: **một class ở lớp ngoài cung cấp method cấp cao "tăng nhịp thở", che 6 nucleus bên trong**. Client chỉ thấy:

```python
# ✓ Client chỉ thấy intent đơn giản
brainstem.increase_breathing_rate(target_rate=20)
```

Bên trong Facade biết phải gọi 6 nucleus theo thứ tự gì. Subsystem nội bộ thay đổi → Facade absorb → client KHÔNG đụng.

### Neuroscience analogy — Brainstem là Facade vĩ đại

Brainstem (medulla, pons, midbrain) chứa hàng chục nucleus quản lý các chức năng vital tự động:

| Nucleus | Chức năng |
|---------|-----------|
| **Nucleus Tractus Solitarius (NTS)** | Trung tâm visceral afferent — nhận tín hiệu baroreceptor, chemoreceptor, taste |
| **Nucleus Ambiguus** | Vagal motor output — heart rate, swallowing, larynx |
| **Pre-Bötzinger Complex** | Pacemaker chính cho nhịp thở (inspiration) |
| **Bötzinger Complex** | Coordinate expiration phase |
| **Parafacial Respiratory Group** | Active expiration khi cần (vd: thở mạnh) |
| **Rostral Ventrolateral Medulla (RVLM)** | Sympathetic vasomotor output — BP control |
| **Caudal Ventrolateral Medulla (CVLM)** | Inhibit RVLM khi cần giảm sympathetic |
| **Locus Coeruleus** | Norepinephrine arousal (đã gặp ở Lesson 01) |
| **Raphe nuclei** | Serotonin — mood, sleep, pain |
| **Area Postrema** | Vomiting reflex trigger (ngoài BBB!) |
| **Periaqueductal Gray (PAG)** | Pain modulation, fear response coordination |
| **Reticular Formation** | Arousal, consciousness, sleep-wake |

Tổng cộng > 30 nucleus, tương tác với nhau qua nhiều pathway.

**Cortex (high-level decision making) KHÔNG biết chi tiết nội bộ này**. Cortex chỉ phát "intent" cấp cao:

| Intent từ cortex | Brainstem dispatch xuống |
|------------------|--------------------------|
| "Tôi đang chạy bộ" | ↑ HR (nucleus ambiguus ↓ vagal), ↑ BP (RVLM), ↑ breathing rate (pre-Bötzinger) |
| "Tôi đang ngủ" | ↓ arousal (LC suppress), ↓ HR, switch sang parasympathetic |
| "Tôi gặp nguy hiểm" | Fight-or-flight: amygdala → PAG → autonomic + motor coordination |
| "Tôi cần nuốt" | NTS + nucleus ambiguus + reticular formation phối hợp 26 cơ |
| "Tôi cần giữ thăng bằng" | Vestibular nucleus + cerebellum + reticular formation |

Cortex giao "mệnh lệnh", brainstem làm orchestration nội bộ. Đây chính là Facade pattern ở quy mô não bộ — trải qua hàng triệu năm tiến hóa, não đã chọn thiết kế tách "decision making" (cortex) khỏi "vital function execution" (brainstem facade).

**Quan sát kiến trúc**:
- Cortex có thể "override" một số chức năng brainstem (vd: voluntary breath holding) — nhưng chỉ trong giới hạn an toàn. Brainstem có "veto power" — bạn không thể nhịn thở chết.
- Khi cortex offline (ngủ sâu, gây mê, coma), brainstem facade vẫn duy trì vital functions độc lập.
- Subsystem nội bộ brainstem có thể **thay đổi cấu trúc** qua tiến hóa (vd: pre-Bötzinger pacemaker được phát hiện ~1991, nhưng chức năng "duy trì breathing rhythm" đã có hàng triệu năm) — Facade interface ổn định, internals tiến hóa.

### Phân biệt với các pattern liên quan

| | Facade | Adapter (06) | Mediator (17) | Decorator (09) |
|---|--------|--------------|---------------|-----------------|
| Mục đích | Đơn giản hóa subsystem | Đổi interface | Decouple components nội bộ | Thêm hành vi |
| Số class wrap | Nhiều (subsystem) | 1 (adaptee) | Nhiều (peer-to-peer) | 1 (chain) |
| Hướng | Client → subsystem (1 chiều) | Client ↔ adaptee (translation) | Components ↔ components (n chiều) | Client → wrapped (chain) |
| Interface mới | Có (đơn giản hơn) | Có (target) | Không (chỉ điều phối) | Không (giữ nguyên) |

Lưu ý phổ biến — confuse Facade với Adapter:
- **Adapter**: 1 class A (adaptee), client cần interface B → Adapter dịch A→B. Translation 1-to-1.
- **Facade**: nhiều class (A, B, C, D...), client cần interface đơn giản → Facade tổng hợp. Aggregation 1-to-many.

---

## Mức 2 — ALGORITHM (Thuật toán)

### Cấu tạo (5 chiều theo framework Ellumm)

| Chiều | Nội dung |
|-------|----------|
| **Cấu tạo** | (a) Subsystem classes (NTS, RVLM, ambiguus, pre-Bötzinger, ...), (b) Facade class (BrainstemFacade) tham chiếu các subsystem, (c) Client (Cortex) chỉ tương tác với Facade |
| **Vị trí** | Boundary giữa client domain và subsystem. Thường ở "module entry" của subsystem. |
| **Chức năng** | Orchestration nội bộ subsystem theo workflow chuẩn, expose 1 interface đơn giản. |
| **Kết nối** | Client → Facade → (orchestration đa chiều) → Subsystem classes. |
| **Ý nghĩa** | Tách concern: client decision-making, Facade orchestration, subsystem execution. Giảm coupling từ M×N xuống M+N. |

### Sơ đồ

```
                 ┌───────────────────────┐
                 │      Cortex (client)  │
                 │  high-level intent    │
                 └───────────┬───────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │   BrainstemFacade        │
              │ + increase_breathing()   │
              │ + arousal_up()           │
              │ + relax()                │
              │ + initiate_swallow()     │
              │ + respond_to_stress()    │
              └────┬───────┬──────┬──────┘
                   │       │      │   (orchestration)
        ┌──────────┘       │      └─────────────┐
        ▼                  ▼                    ▼
┌──────────────┐   ┌──────────────┐    ┌──────────────────┐
│PreBötzinger  │   │   NTS        │    │ Nucleus Ambiguus │
│Complex       │   │              │    │                  │
└──────────────┘   └──────────────┘    └──────────────────┘
   ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
   │RVLM          │  │BötzingerCx   │  │  Locus Coeruleus │
   └──────────────┘  └──────────────┘  └──────────────────┘
   ... (subsystem có thể có 10-30 class) ...
```

### Logic vận hành

```
cortex.want_to_run():
    self.brainstem.increase_breathing_rate(target=20)
    self.brainstem.elevate_BP(percent=15)
    self.brainstem.arousal_up(strength=0.4)

brainstem.increase_breathing_rate(target=20):
    self._pre_botzinger.set_pace(target)
    self._botzinger.coordinate_expiration(target)
    self._nts.adjust_chemoreceptor_gain(0.7)
    self._parafacial.activate_when_needed(threshold=25)
    return current_state()

# Client KHÔNG bao giờ thấy các nucleus.
```

### Thiết kế Facade — các quyết định quan trọng

**1. Stateless vs Stateful**

- **Stateless Facade**: chỉ orchestrate, không lưu state riêng. Subsystem classes giữ state.
  - Ưu: dễ test, không có lifecycle management.
  - Nhược: client phải pass state qua mỗi call.

- **Stateful Facade**: lưu trạng thái cấp cao (current_arousal, current_breathing_mode).
  - Ưu: client gọi đơn giản hơn.
  - Nhược: Facade dần thành God Object nếu không kiểm soát.

Não brainstem là **stateful** — nó duy trì baseline cho tất cả vital functions. Cortex chỉ gửi delta ("increase by X%").

**2. Có cho phép client truy cập subsystem trực tiếp?**

GoF không cấm. Trong Python, một số pattern cho phép:
```python
brainstem = BrainstemFacade()
brainstem.increase_breathing_rate(20)        # high-level

# Advanced user có thể đào sâu khi cần:
brainstem.subsystems.pre_botzinger.set_pacemaker_burst_pattern(...)
```

Sinh học analogy: cortex thường KHÔNG override brainstem, nhưng có thể trong giới hạn (voluntary breath holding) — Facade KHÔNG cấm tuyệt đối, chỉ KHUYẾN KHÍCH dùng interface chính.

**3. Multiple Facade cho cùng subsystem?**

Một subsystem có thể có nhiều Facade phục vụ các persona client khác nhau:
- `BrainstemAutonomicFacade` cho hypothalamus client.
- `BrainstemMotorFacade` cho cortex motor area client.
- `BrainstemEmotionalFacade` cho amygdala/PAG client.

Tương đương trong code: REST API + GraphQL API + gRPC API có thể là 3 Facade khác nhau cho cùng business logic core.

### Anti-pattern: Facade → God Object

Facade dễ phình to. Khi nào nó trở thành anti-pattern:

| Triệu chứng | Hành động |
|-------------|-----------|
| Facade > 500 dòng | Tách thành nhiều Facade theo concern |
| Facade biết về > 15 subsystem class | Có thể cần thêm 1 lớp trung gian |
| Mọi method gọi > 5 subsystem class | Subsystem cần refactor, không phải Facade |
| Client muốn override subsystem behavior | Suy nghĩ Strategy hoặc Bridge thay vì sửa Facade |

Brainstem trong não tránh God Object bằng cách **không tự đưa ra quyết định** — nó chỉ thực thi intent từ cortex/hypothalamus. Logic ra quyết định nằm ở caller.

### Nguyên lý liên quan

- **Law of Demeter**: client chỉ "nói chuyện" với Facade trực tiếp, không reach-through subsystem internals.
- **Single Responsibility**: Facade chịu trách nhiệm orchestration; subsystem class chịu trách nhiệm execution.
- **Open-Closed**: thêm subsystem class mới = sửa Facade nếu cần expose, không sửa client.

---

## Mức 3 — PSEUDOCODE + PYTHON

### Pseudocode

```
class BrainstemFacade:
    field _pre_botzinger, _botzinger, _nts, _ambiguus, _rvlm, _cvlm, _lc, ...

    function increase_breathing_rate(target_rate):
        self._pre_botzinger.set_pace(target_rate)
        self._botzinger.coordinate_expiration(target_rate)
        self._nts.adjust_chemoreceptor_gain(0.7)
        if target_rate > 25:
            self._parafacial.activate_active_expiration()
        return self.respiratory_state()

    function arousal_up(strength):
        self._lc.release_norepinephrine(target=baseline + strength * 60)
        self._raphe.modulate_serotonin(state="active")
        self._reticular_formation.elevate_arousal(strength)
        return self.arousal_state()

    function respond_to_stress(intensity):
        self._lc.release_norepinephrine(target=85)
        self._rvlm.elevate_sympathetic_outflow(intensity)
        self._cvlm.suppress_inhibition()
        self._ambiguus.reduce_parasympathetic_tone(intensity)
        self._pag.coordinate_freeze_or_flight(intensity)
        # Single API call → 5+ nucleus orchestrate
```

### Python (xem file `10_facade.py`)

File code triển khai:
1. **Anti-pattern**: cortex client phải gọi 6+ nucleus trực tiếp với thứ tự đúng.
2. **8 subsystem class** mô phỏng các nucleus brainstem với state riêng.
3. **BrainstemFacade** với 6 high-level method che internals.
4. **Cortex client** chỉ tương tác với Facade — không import nucleus class nào.
5. **Demo subsystem swap**: replace `PreBötzingerComplexV1` bằng `V2` không sửa Cortex client.
6. **Demo brainstem stroke**: phá Facade → cortex còn nguyên nhưng vital functions sụp.
7. **Demo locked-in syndrome**: cortex còn ý thức, descending pathway gãy → bệnh nhân chỉ cử động được mắt.
8. **Ellumm version**: `EllummCore` Facade với 4 internal subsystem (memory, emotion, attention, learning) expose `process_stimulus()`, `recall()`, `dream()`, `report_state()`.

---

## 3 LOẠI VÍ DỤ

### Ví dụ 1 — Vận hành thường

Bạn nhận tin nhắn "ngày mai họp 6h sáng". Cortex prefrontal "lo lắng" → trigger autonomic stress response. Quy trình:

1. **Cortex (client)** gọi `brainstem.respond_to_stress(intensity=0.4)`.
2. Bên trong Facade orchestrate:
   - `LC.release_norepinephrine(target=70)` → arousal tăng.
   - `RVLM.elevate_sympathetic_outflow(0.4)` → vasoconstrict, BP tăng nhẹ.
   - `Nucleus_Ambiguus.reduce_parasympathetic_tone(0.4)` → HR tăng.
   - `NTS.suppress_baroreflex_temporarily()` → cho phép BP tăng mà không bị reflex.
   - `Pre_Botzinger.modulate_breathing(rate=18)` → thở hơi nhanh hơn.
   - `Raphe.shift_serotonin_pattern("alert")` → mood alert.
3. Facade return state hiện tại để cortex biết phản ứng đã xảy ra.

Cortex không cần biết tên nucleus, không cần biết thứ tự setup, không cần biết NTS phải suppress baroreflex (nếu không, cortisol elevation gây dao động BP ngắt quãng vì baroreflex cứ "kéo BP về"). Tất cả những phối hợp tinh vi này nằm trong Facade.

### Ví dụ 2 — Hỏng / Thiếu

**Trường hợp sinh học — Brainstem stroke**: phổ biến gây tử vong vì Facade chính bị phá. Cortex còn nguyên (không thiếu máu) nhưng:
- Không có pacemaker breathing → bệnh nhân ngừng thở (apnea) trong vài phút mà không có máy thở.
- Không có vasomotor control → BP sụp.
- Không có sympathetic/parasympathetic balance → HR rối loạn.
- Mất swallow reflex → aspiration pneumonia.

Đây là minh chứng "Facade là single point of failure" — phá Facade phá cả ứng dụng dù subsystem classes (cortex, vital organs) còn nguyên.

**Locked-in syndrome (tổn thương ventral pons)**: hiếm hơn nhưng đáng sợ hơn về khía cạnh ý thức. Bệnh nhân:
- Cortex hoàn toàn tỉnh táo, ý thức nguyên vẹn.
- Cảm giác (sensory) bình thường — vẫn nghe, nhìn, cảm nhận.
- Brainstem facade nguyên (vẫn thở, tim đập, vital functions OK).
- **Descending corticospinal pathway gãy** → cortex không thể gửi intent xuống brainstem motor + spinal cord cho voluntary muscles.

Bệnh nhân chỉ cử động được mắt (pathway riêng từ midbrain). Đây là "interface vẫn còn nhưng đường dây nối client → Facade bị cắt".

**Trường hợp code — God Object Facade**:
Một startup có Facade `BackendService` ban đầu 5 method, sau 2 năm phình thành 200 method, biết về 50 subsystem class. Mỗi developer thêm method mới khi cần. Test khó (phải mock 50 dependency), refactor không nổi, deploy đau. Facade trở thành cản trở duy nhất giữa client và subsystem — tệ hơn cả không có Facade. Dấu hiệu: bất kỳ thay đổi nhỏ nào cũng phải đi qua "cô gác cổng god".

### Ví dụ 3 — Ứng dụng Ellumm

Ellumm có 4 subsystem chính, mỗi cái 5-10 class:
- **MemorySubsystem**: encoder + storage + retriever + consolidator + index.
- **EmotionSubsystem**: amygdala_salience + insula_interoception + valence + arousal + cortisol_axis.
- **AttentionSubsystem**: bottom_up_salience_map + top_down_priority + IOR_tracker + attention_allocator.
- **LearningSubsystem**: hebbian + LTP + LTD + meta_learning_controller.

Client (REPL, web UI, automation script) cần interface đơn giản:

```python
core = EllummCore()

# Không cần biết 30+ class internal:
core.process_stimulus(stimulus)
core.recall("snake yesterday")
core.dream()                    # consolidation cycle
core.report_state()
```

Bên trong `process_stimulus()`:
1. Attention subsystem assess salience.
2. Nếu salience cao, Memory subsystem encode.
3. Emotion subsystem tag với valence/arousal.
4. Learning subsystem update weight nếu Hebbian condition.
5. Tất cả phải đúng thứ tự: emotion tag trước memory encode, learning sau memory commit.

User của Ellumm không cần biết logic phối hợp này. Khi Ellumm v2 đổi thuật toán salience từ `BottomUpV1` sang `BottomUpV2_attention_aware`, không user nào phải sửa code.

Lợi ích cụ thể:
- **Onboarding**: dev mới chỉ cần học 6 method Facade thay vì 30 class internal.
- **Test**: test Facade end-to-end, mock từng subsystem riêng.
- **Migration**: refactor subsystem nội bộ — Facade absorb breaking changes.
- **Multiple persona**: nếu có CLI client, web client, plugin SDK — tất cả qua cùng Facade hoặc Facade chuyên biệt.

---

## TÓM LẠI

Facade = **một interface đơn giản phía trước subsystem phức tạp**. Trong não, brainstem là Facade vĩ đại — che hàng chục nucleus tự động (NTS, RVLM, pre-Bötzinger, nucleus ambiguus, ...) sau interface đơn giản mà cortex/hypothalamus có thể "nói": tăng nhịp thở, giảm arousal, respond to stress. Tiến hóa đã chọn thiết kế này để cortex tập trung vào decision-making, brainstem lo orchestration vital. Brainstem stroke gây tử vong vì Facade là single point of failure; locked-in syndrome cho thấy cortex còn nguyên không cứu được khi đường dây client→Facade bị cắt.

Dấu hiệu cần Facade:
- Subsystem có > 5 class với coupling phức tạp.
- Client phải nhớ thứ tự setup hoặc lifecycle của subsystem classes.
- Có nhiều client khác nhau dùng cùng subsystem theo cùng workflow.
- Đang xây library/framework — user không cần biết internals.

Cặp pattern thường đi cùng:
- **Facade + Singleton** (lesson 01): thường có 1 Facade instance duy nhất cho subsystem.
- **Facade + Factory Method** (lesson 02): Facade tạo subsystem object từ factory.
- **Facade + Mediator** (lesson 17): Facade là 1-chiều (client → subsystem); Mediator 2-chiều (peer ↔ peer trong subsystem).
- **Facade + Adapter** (lesson 06): Facade có thể wrap legacy subsystem qua Adapter chain.

Anti-pattern cảnh báo:
- **God Object Facade**: hơn 500 dòng, biết về > 15 subsystem class → tách thành nhiều Facade theo concern.
- **Leaky Facade**: lộ subsystem internals qua return type → coupling không giảm.
- **Facade with side-effects in constructor**: khó test, khó mock.

### Câu hỏi tự kiểm tra

1. Khi nào nên cho phép client bypass Facade và truy cập subsystem trực tiếp? Não cho phép cortex "override" brainstem trong giới hạn — bài học gì cho code?
2. Trong Ellumm, nếu một advanced user muốn custom thuật toán encode (vd: nghiên cứu thí nghiệm), họ phải làm sao mà không phá Facade interface? (Gợi ý: Facade + Strategy + Dependency Injection)
3. Facade và Mediator (lesson 17) đôi khi confuse. Trong não, brainstem là Facade nhưng cũng có thể coi là Mediator giữa các nucleus. Phân biệt rõ: khi nào gọi là Facade, khi nào là Mediator?
