# Decision Register

---
id: DEC-1
status: active
date: 2026-06-25
actor: "user:uspro"
ts: "2026-06-25T14:37:14.561440+00:00"
affects: "docs/,plans/,MAP.md,docs/spec/,docs/roadmap/"
---

## DEC-1 — Cấu trúc docs/ theo Diátaxis-hybrid; tách docs(spec) / plans(thực thi) / docs-roadmap(tương lai); bỏ lớp per-module mirror-source

docs/ trộn 5 loại không phân tầng + lớp per-module nhúng full code rot ngay + 2 cặp trùng lặp. Áp Diátaxis (tutorial/how-to/reference/explanation) + giữ epic spec; per-module dựa MAP.md auto-gen, chỉ giữ explainer cho module lõi (KNOWN_RISKS); current(E21)=spec/active, future(E11-E15,E20)=roadmap/future kèm dependency-map làm cổng vào /hs:plan.

---
id: DEC-2
status: active
date: 2026-06-25
actor: "user:uspro"
ts: "2026-06-25T14:48:55.723933+00:00"
affects: "supervisor/graph.py,supervisor/contracts.py,supervisor/loop.py,supervisor/state.py,control/commands.py,control/command_registry.py,config/runtime_command_types.yaml,roles/spec.py,roles/registry.py,plans/"
---

## DEC-2 — Delegation linh hoạt qua control plane E21 (hướng C đầy đủ): O là delegator duy nhất; department = alias gom role chạy tuần tự và TỰ kéo member chưa-compose vào team; roster-growth + department đều đi qua RuntimeCommand AddAgentToLoop + pending_commands, apply tại safe checkpoint cuối round

Mục tiêu: cho Agent-O linh hoạt chỉ định agent/department lúc chạy. Chốt qua brainstorm: giữ O-only (không recursive agent-picks-agent), department là alias tuần tự (không parallel/sub-loop), roster catalog + thêm tại checkpoint. Chọn hướng C (E21-first) thay vì A (field ad-hoc) để có MỘT đường duy nhất cho cả O lẫn human-UI mutate team -> DRY; idempotency_key + issued_by audit lấy miễn phí từ contract đã ship (control/commands.py, control/command_registry.py); và advance E21 từ contract-only sang runtime consumer đầu tiên (pending_commands vào _state_view supervisor/graph.py:124-131 + apply_pending_commands tại checkpoint trong _drive). Department được tự kéo agent mới: target department ngầm phát AddAgentToLoop cho member chưa nằm trong selected_agents, rồi expand thành 1 delegate() mỗi member trước authority gate (supervisor/graph.py:142-147). LOẠI hướng B (coordinator handler ở delegation seam) vì phá invariant no-nested-subloop + mất audit/scope per-member. Guardrails: depth không đổi; scope mỗi member chỉ narrow (delegation/policy.py:25-27); apply command CHỈ ở cuối round sau judge_acceptance (không phá resume; pending_commands persist cùng selected_agents); idempotent theo key (control/commands.py); catalog-bound (tái dùng validator compose_team graph.py:93-97); authority gate vẫn là nguồn chân lý sau expansion. Seam delegation + bootstrap agent:general GIỮ NGUYÊN (không unfreeze registry).

---
id: DEC-3
status: active
date: 2026-06-25
actor: "user:uspro"
ts: "2026-06-25T14:53:50.862104+00:00"
affects: "docs/system-architecture.md,docs/code-standards.md,docs/reference/"
---

## DEC-3 — system-architecture.md + code-standards.md giữ ở docs/ root (KHÔNG move vào reference/) — bảo toàn harness self-hosting standards contract

harness/standards/README.md ghi rõ repo self-hosting đọc standards tại docs/system-architecture.md + docs/code-standards.md; hs:plan/hs:cook tham chiếu 2 path này. Move vào reference/ phá contract. Đánh đổi: hơi lệch Diátaxis thuần (standards nằm cạnh root docs/) đổi lấy không vỡ wiring. reference/ + docs/README.md trỏ tới thay vì relocate.

---
id: DEC-4
status: active
date: 2026-06-25
actor: "user:uspro"
ts: "2026-06-25T16:28:49.464770+00:00"
affects: "docs/roadmap/future/,docs/roadmap/dependency-map.md,docs/roadmap/project-roadmap.md,docs/spec/active/E21-realtime-control-plane/"
---

## DEC-4 — E15 Self-eval bỏ khỏi roadmap/future (verdict merge-into-other → gộp E21); sửa map-drift E15 deps E16→E21

Critique workflow: governance/audit của E15 đã bị E21 S21.33 nuốt (evidence types + AC report); phần judge≠doer rẻ nhất là siết judge_acceptance (supervisor/graph.py:238) trong E21, không cần epic riêng. Bảng 01_BUILD_ORDER:23 còn ghi E15→E16 trong khi E16 đã gộp E21 (map tự mâu thuẫn) → sửa thành E04,E10,E21. User chốt 'bỏ đi'.

---
id: DEC-5
status: active
date: 2026-06-25
actor: "user:uspro"
ts: "2026-06-25T16:28:49.540554+00:00"
affects: "docs/roadmap/future/E11-departments.md,docs/roadmap/future/E12-router-supervisor.md,docs/roadmap/future/E13-software-factory.md,docs/roadmap/README.md"
---

## DEC-5 — Roadmap routing-cluster: ranh giới E12/E13 + mồi phá vòng E11↔E12

Synthesis phát hiện 2 tension cứng: (1) E12 'plan nhiều bước' chồng vai E13 'dây chuyền cố định' → chốt định nghĩa load-bearing: multi-step trong-MỘT-task = E13 (pin_route), dispatch nhiều-TASK = E12 (GlobalSupervisor). (2) Deadlock ngưỡng: E12 chờ E11 ship nhưng trigger mạnh nhất của E11 là 'E12 in-progress' → nguyên tắc phá vòng: E11 rã đông MỨC TỐI THIỂU (DepartmentRegistry+validate, roles/spec.py:104) ngay khi E12 vào THIẾT KẾ, không chờ E12 chạy hẳn. Ghi để Thaw Protocol Bước 2 áp.

---
id: DEC-6
status: active
date: 2026-06-26
actor: "user:uspro"
ts: "2026-06-25T19:02:22.913278+00:00"
affects: "control/snapshot.py,control/commands.py,supervisor/state.py,ui/control-plane/,config/runtime_event_types.yaml,config/runtime_command_types.yaml,plans/"
---

## DEC-6 — E21 build UI-first trên fake backend: fake = HTTP/SSE server Python reuse control/ dataclass (seam by-construction, đổi backend = đổi URL); stack React+Vite+TS (React Flow + tanstack-virtual); lát 1 = full T1 (Graph/Timeline/Inspector/Approval) + prompt box & Send; tạo TaskLoopSnapshot + CommandAck dataclass TRƯỚC khi viết UI; UI mới sống song song console cũ (không sửa ui/server.py)

Đảo thứ tự so với discovery brief (spine-backend-first) nhưng KHÔNG xây trên facade: fake chạy Redactor().apply() + .as_dict() thật nên secret không rò và 'drop-in khi đấu nối' là bảo đảm bằng cấu trúc, không bằng kỷ luật. 2/5 shape (TaskLoopSnapshot, CommandAck) chưa có dataclass → phải tạo trước (dataclass-only, không wire) nếu không seam còn lỗ by-discipline. React vì reader junior cần ecosystem/ví dụ. Done = demo fixtures + contract-seam test (UI chỉ đọc ui_payload, không đọc payload raw).

---
id: DEC-7
status: active
date: 2026-06-26
actor: "user:uspro"
ts: "2026-06-25T20:06:12.664866+00:00"
affects: "supervisor/evidence.py,supervisor/graph.py,supervisor/loop.py"
---

## DEC-7 — S21.33 evidence-type gate: derived-from-kind + >=1-valid quantifier + trust-worker

evidence_type derived tu artifact.kind (khong luu tren AcceptanceCheck -> 0 migration); NON_EVIDENCE_KINDS={session_plan,context_packet,ac_report}; kind rong->None; kind-la-worker->artifact (trust-worker, threat model = O mis-cite scaffolding); judge_acceptance passed = all-exist + >=1-valid-type (spec S21.33, KHONG all-valid, red-team FM-HIGH); ac_report id=ac_report-{session_id}. Chon H2 re-scope thay command-based vi command_bridge/pending_commands khong ton tai tren branch feat/docs-diataxis-restructure.

---
id: DEC-8
status: active
date: 2026-06-26
actor: "user:uspro"
ts: "2026-06-25T21:09:30.228891+00:00"
affects: "control/authz.py,control/commands.py,control/permission.py,docs/explanation/authz-vs-attribution.md"
---

## DEC-8 — attribution≠authz: issued_by/Actor là ghi nhận, không phải quyền; permission-edit (UpdateAgentPermission→can_modify_permissions) cần human RuntimeCheckpoint kể cả dưới trust-O

Harness tuyên bố actor≠authz vì là tool hợp tác; hex_agent xây authz THẬT nên port sự phân biệt và ĐẢO kết luận: authz quyết bởi requires_permission+checkpoint, không phải claim của issuer. requires_permission mới khai báo (runtime_command_types.yaml) chưa thực thi; command_bridge vắng trên branch (DEC-7). Phase 1 chỉ doctrine+predicate thuần (control/authz.py), enforcement hoãn cho epic command-application.
