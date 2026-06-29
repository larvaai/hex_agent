---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Critique hợp nhất — báo cáo "drag_from_zero authoring UI"

Artifact: `plans/reports/ui-critique-260626-2335-drag-from-zero-authoring-ui-report.md` (direction-to-commit).
Mode: advisory (không ghi gate artifact). Lenses: red-teamer · independent-revalidator · brainstormer. 2026-06-26.

## Verdict: BLOCKED

Đừng commit hướng trong báo cáo như đang viết. Hai blocker `proven` sống sót sau hợp nhất; đường đi đúng rẻ hơn nhiều đang bị bỏ qua. **Chẩn đoán của báo cáo đúng — đơn thuốc sai.** Reverse sequencing + hạ modality + viết lại quanh 3 quyết định ở cuối.

Severity sau merge: blocker 2 · major 4 · minor 3 · (precision 2). independent-revalidator tái-suy-luận độc lập 7/7 claim chịu lực → CONFIRM toàn bộ, 0 overturn; nó là lens *củng cố*, nâng các finding lên `proven`.

## Bảng finding hợp nhất (xếp hạng)

| # | Severity | Lens | Root cause | Anchor | Fix |
|---|---|---|---|---|---|
| 1 | **BLOCKER** ×3 | red F1+F2+F3, brain F2 | **Lying UI — UI author ra control runtime im lặng vứt.** prompt/skills/rules/tools per-agent, edge, hook/budget per-node: không cái nào được build-path đọc. | `agent.py:34-37` (Agent={id,role,llm}), `wiring.py:77` (chỉ `role`/`entry`), `wiring.py` 0 ref edge, `registries.py:17` (hook key theo phase), `registries.py:67-83` (1 counter `max_llm_calls`, no token/cost) | Enforce-trước-author. Hoặc wire field vào runtime trước, hoặc chỉ expose field engine *đã* consume. |
| 2 | **BLOCKER** | red F4 | **Mid-run injection qua drag-drop = data race.** `join_agent(resume=True)` re-enter `run_until_idle`, mutate `_ready/_waiting/_recs` không lock, trên thread khác run-thread. | `server.py:182` (daemon thread), `server.py:412-413` (ThreadingHTTPServer), `orchestrator.py:61-71` (0 lock) | Command-queue/lock trước khi expose trên live WS. Không phải "differentiator rẻ". |
| 3 | MAJOR | red F7 | **"Swap React Flow" mis-framed về CHI PHÍ — `.dc.html` đã chạy React.** Rủi ro thật là seam DC-template (sc-for/x-dc, bun-built) ↔ JSX, không phải đổi renderer. | `support.js:9-19` (getReact/createElement), `Agent IDE.dc.html:519` | Reframe rủi ro về seam template↔JSX; định lượng trước khi recommend. |
| 4 | MAJOR | red F6 | **Báo cáo dẫn `project-data.js` như "spec đúng" nhưng đó là demo free-text bịa** — chứa "Decompose into a LangGraph", nghịch memory DROP-langgraph. | `project-data.js:197-248` | Gỡ trích dẫn này khỏi cơ sở lập luận; lấy schema từ `topology.py` + cái `wiring` consume. |
| 5 | MAJOR | red F5 | **exec-node→topology-node back-link là many-to-one + null ở root**, không phải addition 1:1. | `read_model.py:22,36,41,55` (key theo task_id; `agent_id` là link duy nhất, `None` ở root) | Thừa nhận mapping partial; xử lý null/many trước khi build inspector. |
| 6 | MAJOR | brain F1 | **Drag-drop KHÔNG phải MVP — JSON-first + Run là 80/20 bị bỏ qua.** Topology đã round-trip JSON; `validate()` trả lỗi đọc được; textarea editor đã có. | `topology.py:112-122`, `topology.py:80-109`, `Agent IDE.dc.html:128,402` | Ship JSON-first: `GET/PUT /api/topology` + validate + `POST /api/runs` + trỏ textarea vào topology JSON. |
| 7 | minor | red F8 | **`memory` node author được nhưng unwired** — 1/5 palette type là dead node. | `wiring.py:70-71` (`pass`) | Ẩn/đánh dấu placeholder tới khi wire. |
| 8 | minor | brain F3 | **Full React Flow + 4 tier + undo/marquee/persist nghịch memory lean/DROP-70%-LOC.** | memory `[[hex-agent-lessons-to-carry]]` | Cắt về modality rẻ nhất (JSON/form); React Flow chỉ khi user thật cần. |
| 9 | minor | red F9 | **Concurrent PUT topology trên single-process server chưa test** (write route chưa tồn tại). | (no write route yet) | Thêm test khi viết route. |

**Precision corrections (LOW — sửa câu chữ báo cáo gốc, không đổi kết luận):**
- C1 — `report:81` gọi `ui_drag/` "bản sao y hệt": chỉ `project-data.js` giống; `ui_drag/Agent IDE.dc.html:434-436` KHÁC và *có* wire project-data (`buildNodes(AGENTS)`). ui_drag là VARIANT, không phải dead duplicate → đừng "dọn vụn → delete" kẻo xóa nhầm reference.
- C2 — `report:37` mô tả drawer `rules` chỉ là verdict-evidence; thực tế là ternary `Agent IDE.dc.html:696` (`rt.evidence ? split : node.done_when.map(checkLabel)`) — thiếu nhánh fallback. Kết luận "relabel field exec-tree" vẫn đứng.

## 3 quyết định kiến trúc cần chốt (DEC-worthy)

- **DEC-A — Sequencing: verifier-first hay authoring-first.** Blocker #1 + brain F2 hàm ý: build verifier/enforcer thật (Slice 6b, plan `plans/260626-1528-decompose-agent-recursion-slice/`) TRƯỚC, rồi authoring — không thì UI "nói dối".
- **DEC-B — Modality: JSON-first vs visual canvas.** Xếp hạng brain: A(JSON-first, low) > B(form, med) > C(chat, med-high) > D(React Flow, high/anti-lean).
- **DEC-C — Có expose mid-run injection trên live run không**, với điều kiện thêm lock/command-queue trước (blocker #2).

## Báo cáo ĐÃ ĐÚNG (giữ, đừng vứt cả cụm)

- Chẩn đoán hiện trạng chính xác từng dòng: UI là observer thuần (Đồ thị 2, zero authoring); drawer *fake* skills/hooks/rules (`:643-645,:701-703`); server không topology route (`:325-359`); chat `send()` chỉ gọi `run()` (`:478-484`). Tất cả CONFIRM.
- Khoảng trống observer→authoring là hướng có giá trị; mid-run injection *là* feature backend thật — chỉ cách expose sai.
- Tier hóa là khung tư duy hợp lý; chỉ cần đảo ưu tiên + hạ modality, không vứt khung.

## Đường reframe đề xuất (đảo ngược báo cáo)

1. **Slice 6b verifier thật trước** — `mu`/`done_when`/`verdict` đang stub là gap lớn nhất (codebase-map `:100`); không có máy thì authoring vô nghĩa.
2. **JSON-first authoring** (DEC-B = A): 3 route + trỏ textarea sẵn-có vào topology JSON; lock Run tới khi `validate()` sạch. Đóng full vòng compose→run→observe, surface nhỏ nhất, khớp lean.
3. **Mid-run injection = 1 route có concurrency-guard**, không phải canvas Tier 3.
4. **Form-based (B)** chỉ khi user vấp cú pháp JSON; **React Flow (D)** chỉ khi topology phức tạp cần debug bằng mắt — chưa tới ngưỡng.

## Unknowns

- React Flow nhúng vào framework DC khả thi tới đâu — `support.js` (1595 dòng) chưa đọc sâu; cần spike trước nếu DEC-B chọn D. [UNVERIFIED]
- `memory` node wiring (`wiring.py:70`) — placeholder, author được nhưng chạy chưa ra gì.
- Concurrent PUT topology trên `ThreadingHTTPServer` — chưa reproduce vì write-endpoint chưa tồn tại.
