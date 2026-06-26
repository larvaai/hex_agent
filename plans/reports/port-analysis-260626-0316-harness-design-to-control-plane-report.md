---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Port analysis — Harness design → hex_agent control plane

**Mode:** `--improve` (cross-domain pattern port, not code copy) · **Skill:** `hs-create:port`
**Source:** `./harness` (vendored Claude Code SDLC harness) · **Target:** hex_agent kernel (`control/`, `safety/`, `middleware/`, `observability/`)
**Date:** 2026-06-26 · **Branch:** feat/docs-diataxis-restructure · **Risk score:** Low (1 critical assumption — resolve first)

---

## TL;DR (cho lead)

Harness và hex_agent **xây cùng một loại hệ thống**: một control plane gate/policy/telemetry cho agent. Harness gate tool-call của Claude Code bằng hook ngoài tiến trình; hex_agent gate tool-call của kernel riêng bằng middleware trong tiến trình. Vì vậy giá trị port là **kỷ luật thiết kế đã chín**, không phải code.

Phần lớn cơ chế hex_agent **đã có** (JSONL audit, codegen drift-guard `--check`, config-as-YAML registry). Ba thứ đáng port — tất cả nhỏ, có thể đảo ngược:

1. **Doctrine "ba sự thật" — đảo ngược kết luận** (rủi ro cao nhất, chi phí gần như 0). Harness nói "actor = attribution, không phải authz". hex_agent xây authz **thật** (`Permission.can_modify_permissions`), nên phải port *sự phân biệt* nhưng **đặt quyết định authz ra ngoài tầm với của agent**.
2. **Kỷ luật verdict nghiệm thu** (P3) — khớp đúng việc đang làm trên nhánh (S21.33): verdict enum `PASS / PASS_WITH_RISK / BLOCKED`, **chính sách verdict nằm trong code**, `PASS_WITH_RISK` ≠ đậu.
3. **Posture thất bại của middleware** (P1) — `middleware/policy.py` hiện là deny-list trần; gắn mỗi gate một posture tường minh + bất biến "gate blocking mà ném exception = từ chối (fail-closed)".

**Không port:** lớp hook ngoài tiến trình (kernel đã có chokepoint `core/kernel.execute_tool`), lớp YAML mode/preset (thừa cho 5 middleware), port quy trình rules-doc (đó là việc docs, đang chạy Diátaxis riêng).

---

## 1. Source manifest

| Trường | Giá trị |
|---|---|
| Nguồn | `harness/` (vendored, self-contained) |
| Phạm vi | hooks architecture, telemetry/state, rules layer, skills, config-as-data, schemas |
| Quy mô | 14 skill dirs · 47 hook files · 26 rules · state JSONL gitignored |
| Ref/SHA | local working tree (không phải remote) |
| Bản chất | Công cụ SDLC **hợp tác** cho dev — nâng chi phí gian lận, không chống kẻ địch |

## 2. Convergence map — 8 pattern của harness → trạng thái hex_agent

| # | Pattern harness (evidence) | hex_agent hiện có (evidence) | Verdict |
|---|---|---|---|
| P1 | 3-class hook posture; class là **hằng số code**, config chỉ bật/đổi-mode; compliance fail-closed exit 2 (`harness/hooks/hook_runtime.py:329–417`) | `middleware/policy.py:9–21` deny-list trần; thứ tự middleware ad-hoc (`core/kernel.py` `.use()`); không khai báo posture thất bại | **PORT** |
| P2 | JSONL append-only: actor+ts+**payload_hash sha256-12** (chứng minh nội dung không lưu PII), xoay theo ngày, tracing fail-open (`harness/hooks/trace_log.py:30–87`) | `observability/event_log.py:41–134` JSONL+summary+metrics; redaction tách `ui_payload` (`control/redaction.py:37–73`) — nhưng **chưa có payload_hash làm bằng chứng** | **PARTIAL** (thêm payload_hash) |
| P3 | Presence-gate đọc artifact JSON từ FS; verdict enum, **chính sách verdict trong CODE** (`PASS_WITH_RISK` ≠ đậu) (`harness/hooks/gate_stage.py:149–154`, `schemas/artifact-verification.json`) | `control/checkpoint.py:27–93` status enum; S21.33 đang làm AC report artifact + evidence-type gate (commit `08df3ad`, `8f10d00`) | **PORT (ngay, vào S21.33)** |
| P4 | **Ba sự thật**: gate≠auth, actor≠authz (spoofable), config≠proof (`harness/rules/harness-contract.md:21–34`) | `control/permission.py:19–86` authz **thật** gồm `can_modify_permissions`; `IssuedBy`/`Actor` đi vào lệnh (`control/commands.py:28–53`) | **PORT làm DOCTRINE — đảo kết luận** |
| P5 | Config-as-YAML tracked + validate advisory + preset strict/balanced/lenient; env override **PATH** không phải value | `config/runtime_event_types.yaml` + `runtime_command_types.yaml` nạp bởi registry (hội tụ) | **ĐÃ CÓ** (preset là tùy chọn) |
| P6 | Autonomy `default/ask_all/god` quyết định tất định; **không level nào tự-ship qua gate** (`harness-contract.md:48–52`) | `effective_from` + RuntimeCheckpoint; Gap: orchestration `waiting→approved` chưa nối (Phase B4) | **PORT bất biến** (no-bypass) |
| P7 | Rules load-on-demand + `config-reference` index | Đang restructure docs Diátaxis (commit `99f84ce`) | **SKIP cho kernel** (việc docs) |
| P8 | Codegen tất định + version-stamp + `--check` drift guard | `tools/gen_ts_contracts.py:92–119` đã có `--check`; roundtrip tests | **ĐÃ CÓ** (thêm schema_version stamp) |

## 3. Challenge gate (HARD GATE — 6 câu)

| # | Câu hỏi | Source's answer | Local answer | Rủi ro nếu sai |
|---|---|---|---|---|
| 1 | **Necessity** — cần *cơ chế hook* hay chỉ *ý tưởng*? | Hook ngoài tiến trình vì harness không sửa được core của Claude Code | hex_agent **sở hữu** kernel → đã có chokepoint `core/kernel.execute_tool` | Dựng lớp indirection thừa lên một chokepoint đã tồn tại |
| 2 | **Authz vs attribution** ⚠️ load-bearing | actor spoofable, gate≠auth — chấp nhận được vì **hợp tác** | `Permission.can_modify_permissions` ngụ ý ranh giới tin cậy **thật**; agent có thể tự xin leo quyền | Sao chép thái độ "attribution spoofable là ổn" vào hệ cần authz đối kháng = **leo thang quyền** |
| 3 | **Simpler alternative** — lấy 80% giá trị rẻ hơn? | 3 lớp + config mode YAML | Chỉ cần khai báo posture (advisory/blocking) + fail-closed-on-exception là đủ | Over-engineer lớp YAML mode cho 5 middleware |
| 4 | **Existing overlap** — đã có chưa? | JSONL audit, codegen, config-yaml | **Đã có cả ba** (`event_log.py`, `gen_ts_contracts --check`, registries) | Port lại thứ đã có = churn vô ích |
| 5 | **Blast radius** | Hook ngoài tiến trình, lỗi cô lập | P1/P3/P4 chạm chokepoint kernel + đường authz/acceptance = core data flow | Posture fail-closed sai → chặn tool hợp lệ; verdict policy sai → đậu việc tồi |
| 6 | **Maintenance** | Harness team | Cùng kernel maintainer; doctrine tự-tài-liệu (1 rule doc + comment + test) | Thấp; không dep mới, không service mới |

**Critical count:** 1 (#2 — sai = lỗ hổng bảo mật). Theo thang rủi ro: **Low → Proceed, nhưng giải quyết giả định #2 trước.** Đó chính là nội dung Port A.

## 4. Decision matrix

| # | Quyết định | Source's way | Local way | Hybrid | Rủi ro | **Choice** |
|---|---|---|---|---|---|---|
| 1 | Vị trí thực thi | hook ngoài tiến trình | middleware chokepoint trong kernel | — | low | **local** (giữ chokepoint; chỉ mượn kỷ luật posture) |
| 2 | Posture thất bại | `HOOK_CLASS` hằng số | thứ tự middleware ad-hoc | gắn posture + fail-closed cho gate | low | **hybrid** |
| 3 | Bản ghi audit | actor+ts+payload_hash | JSONL+redaction split | thêm payload_hash | low | **hybrid** |
| 4 | Verdict nghiệm thu | enum, policy trong CODE | S21.33 đang làm | nhận enum + verdict policy code-side | low | **source** (kỷ luật tốt hơn) |
| 5 | Authz vs attribution | spoofable, gate≠auth | Permission là authz thật, có self-modify | port *phân biệt*, authz **ngoài tầm với agent** | **med→critical** | **invert** |
| 6 | Config posture | preset+override YAML | registry từ YAML | preset tùy chọn lên Permission | low | **local** (đã có) |
| 7 | Codegen | stamp + `--check` | `--check` đã có | thêm schema_version stamp | low | **local** (đã có) |

## 5. Lộ trình port đề xuất (3 cái chắc, xếp theo blast-radius tăng dần)

**Port A — Doctrine "ba sự thật" cho control plane** (rủi ro 0, đòn bẩy cao nhất)
- Một explanation doc ngắn (`docs/explanation/...`) + comment trên `control/permission.py` và `control/commands.py`: `IssuedBy`/`Actor` là **attribution, không phải authz**; quyết định authz cho `can_modify_permissions` phải đánh giá ở nơi output của agent không set được.
- 1 test: lệnh `UpdateAgentPermission` do agent tự phát, tự cấp `can_modify_permissions=True`, **bị từ chối trừ khi qua human checkpoint**. Khai thác đúng `RuntimeCheckpoint` đã có.

**Port B — Kỷ luật verdict nghiệm thu vào S21.33** (additive vào việc đang làm)
- Verdict enum `PASS / PASS_WITH_RISK / BLOCKED`; **chính sách verdict nằm trong code**, không trong config; `PASS_WITH_RISK` ≠ đậu. Gate đọc AC report artifact từ FS. Soi gương `gate_stage.py:149–154`.

**Port C — Posture thất bại của middleware** (sau tests)
- Mỗi middleware/gate khai báo posture tường minh (`advisory` | `blocking`) + bất biến "blocking gate ném exception ⇒ deny (fail-closed)". `PolicyGate` lớn lên từ deny-list thành gate posture-aware. Chốt sau `tests_audit/test_middleware_exact_semantics.py`.

**Thêm nhỏ:** payload_hash trong `event_log.py` (P2) · schema_version stamp trên artifact (P8).
**Bỏ:** lớp hook ngoài tiến trình · lớp YAML mode/preset · port quy trình rules-doc.

## 6. Dependency matrix (file đụng tới)

| Port | EXISTS (sửa) | NEW (tạo) | CONFLICT |
|---|---|---|---|
| A | `control/permission.py`, `control/commands.py` | 1 explanation doc, 1 test authz-escalation | — |
| B | gate nghiệm thu S21.33, `control/checkpoint.py` | — | nằm trên nhánh đang mở, phối hợp |
| C | `middleware/policy.py`, `core/kernel.py` | posture constant + test | thứ tự middleware |

## 7. Handoff

Báo cáo này chứa đủ đầu vào cho `hs:plan`: source manifest · convergence map · dependency matrix · decision matrix · risk score. `hs-create:port` **không** implement code.

```
Để biến 3 port (A+B+C) thành plan có rollback: /hs:plan port harness doctrine + acceptance-verdict + middleware-posture vào control plane
Hoặc vì cả ba đều nhỏ: /hs:cook trực tiếp từng cái sau khi plan duyệt
```

## Câu hỏi còn mở

- Port B chồng lên nhánh S21.33 đang mở — làm trong cùng nhánh hay tách? (đề xuất: cùng nhánh, vì cùng chủ đề acceptance gate)
- `effective_from="immediately"` có nên bị cấm cho lệnh do **agent** tự phát (chỉ human checkpoint mới dùng) không? — thuộc Port A, cần xác nhận khi plan.
