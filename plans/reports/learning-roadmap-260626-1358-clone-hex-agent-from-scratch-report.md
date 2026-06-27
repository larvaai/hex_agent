---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Roadmap học clone `hex_agent` từ số 0 — báo cáo bàn giao

**Ngày:** 2026-06-26 · **Nguồn:** brainstorm (`/hs-think:brainstorm`) · **Trạng thái:** đã bàn giao bộ roadmap

## TL;DR

Bàn giao một bộ roadmap dạy người mới dựng lại toàn bộ sản phẩm agent (`hex_agent`) từ con số 0,
chia **7 phase step-by-step**. Mỗi phase: mục tiêu → xây gì → dựng từng bước → class/biến kiểm soát →
invariant → pitfall (triệu chứng/nguyên nhân/cách tránh) → Definition-of-Done (test gate) → bài học kiến trúc.
Mọi luận điểm load-bearing đều **neo vào code thật** (`file:line`), verify trực tiếp trên source — không chép lại doc.

Vào cửa: **[`plans/260626-1358-clone-hex-agent-roadmap/README.md`](../260626-1358-clone-hex-agent-roadmap/README.md)**.

## Hai quyết định định hình bàn giao (user chốt)

| Trục | Chốt | Vì sao |
|---|---|---|
| **Phạm vi** | Toàn bộ sản phẩm, **trừ `harness/`** → P0→P3 (E01–E10) + E21 control plane | `harness/` là tooling SDLC riêng cho Claude Code, không phải sản phẩm agent → đưa vào làm loãng bài học kiến trúc |
| **Độ sâu** | **Phase-guide có code-neo** (index + 7 file/phase, DoD gate, pitfall) | Vừa dạy được "vibe coding có kiến trúc" vừa không phình token như full-tutorial tái dựng từng dòng |

> Đây là quyết định *định dạng bàn giao*, không phải quyết định kiến trúc sản phẩm → **không** ghi DEC mới
> (giữ `docs/decisions.md` DEC-1..8 thuần cho product calls).

## Cấu trúc bộ roadmap

```
plans/260626-1358-clone-hex-agent-roadmap/
├── README.md                          ← index: triết lý + bản đồ phase + bảng I1–I17 + bảng pitfall + quy ước
├── phase-1-microkernel-chokepoint.md  E01+E04  kernel một-cửa + observability
├── phase-2-llm-discipline.md          E03+E02  LLM-as-capability + json_gate/budget/finish-gate
├── phase-3-toolbox-safety.md          E06      sandbox jail + SafeToolPort + middleware chain
├── phase-4-graph-resume.md            E05      LangGraph substrate + SQLite-truth resume
├── phase-5-skills-rag.md              E07+E08  skills progressive-disclosure + RAG health-gated qua ports
├── phase-6-roles-delegation.md        E09+E10  roles allowlist + delegation chokepoint riêng + TaskLoop/acceptance
└── phase-7-control-plane.md           E21      contracts-first + emitter/redaction + UI-on-fake-backend
```

Sợi chỉ xuyên suốt (bảng **I1–I17** trong index) là phần giá trị nhất: mỗi invariant gắn với **biến/hàm cụ thể**
thực thi nó và **mất gì nếu phá** — đây là câu trả lời cho "kiến trúc, cách tổ chức file/class/biến đã giúp kiểm soát thế nào":

- **Một cửa** `execute_tool` (I1) → thêm observability/safety/envelope một lần, áp cho mọi call.
- **`freeze()` + `KernelSession`** (I2,I3) → đóng băng cái chia sẻ, cô lập cái thay đổi → 0 rò state giữa run.
- **`AgentState` serializable-only + SQLite-truth** (I10,I11) → resume an toàn, không chạy lại node side-effect.
- **Delegation chokepoint riêng** (`delegation/manager.py:63`, I13) + **scope con ⊆ cha** (I14) → nhiều agent vẫn audit được, không leo quyền.
- **Redact tại biên** (I16) + **attribution≠authz** (I17) → realtime control mà không rò secret, không tin lời tự khai.

## Phát hiện khi verify (drift giữa doc gốc và code thật)

Quá trình neo `file:line` lộ ra 3 chỗ tài liệu gốc lạc hậu — đáng sửa:

1. **`known-risks.md` cite sai dòng raw-args.** Ghi `core/kernel.py:79-82`, thực tế log raw `args` ở **`core/kernel.py:125`** (`"args": request.args` trong publish `tool.requested`). Pitfall vẫn LIVE, chỉ lệch số dòng.
2. **`test_security_boundaries.py` nằm ở `tests_audit/`**, không phải `tests/` như một số chỗ ngụ ý.
3. **E21 UI build hơn mức brief tưởng.** `ui/control-plane/` (React components thật) + `ui/ide/` (backend live reuse `control/`) đã tồn tại → Phase 7 mô tả UI là "một phần/IDE live", không phải "hoàn toàn pending". Phần thực sự *chưa* có: authz **enforcement** (`command_bridge` vắng trên branch này — DEC-7/DEC-8) và supervisor emitter còn opt-in `default None` (`supervisor/graph.py:48`).

## Cách dùng (lộ trình học)

1. Đọc `README.md` hết — nuốt 3 luật nền + bảng I1–I17 trước khi gõ dòng code nào.
2. Đi tuần tự Phase 1→7. **Không sang phase kế khi DoD chưa xanh** (`python run_smoke.py` + `pytest -q`).
3. Mỗi phase, đối chiếu code-neo với source thật trong repo này như "lời giải" khi kẹt.
4. Khi sửa file dễ vỡ → mở bảng pitfall của phase để biết test nào phải chạy lại.

## Bước kế (đề xuất)

- **Nếu muốn build thật theo roadmap:** `/hs:plan` từng phase (bắt đầu Phase 1) → biến mỗi DoD thành AC + test trước khi cook.
- **Nếu muốn bản full-tutorial** (tái dựng từng dòng cho người copy-paste chạy ngay): mở rộng từng phase file — tốn token hơn nhiều, cân nhắc làm dần theo phase.
- **Vệ sinh repo gốc (tách bạch):** sửa 3 drift ở mục trên (cite dòng raw-args, vị trí test, trạng thái E21 UI) trong `docs/`.

## Câu hỏi mở

- Roadmap dừng ở E21 (sản phẩm hiện tại). Các epic tương lai E11–E14/E20 (`docs/roadmap/future/`) **chưa** đưa vào — đúng ý "clone cái đã làm được", nhưng nếu muốn dạy cả hướng mở rộng thì cần phase 8+.
- Có muốn bản full-tutorial code-từng-dòng cho ≥1 phase nền (Phase 1) làm mẫu không? Quyết định này đổi đáng kể khối lượng.
