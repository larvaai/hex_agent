---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Brainstorm — LangChain / LangGraph / LangFlow vs build-from-scratch (substrate)

Ngày: 2026-06-28 · Hỏi: "có nên dựa vào LangChain/LangGraph/LangFlow để đỡ phải xây lại từ đầu?"
Trạng thái: **đã quyết — re-affirm DEC-11, không relitigate.** Có bằng chứng empirical.

## Bằng chứng có sẵn (không dựng lại)

- DEC-11 — `docs/decisions.md:144` (2026-06-26): Flowise/Langflow/Dify/n8n bị loại (own-UI → canvas của họ là dead weight + UI-lock/license). Build spec/safety layer + runtime; chỉ spike Burr cho FSM.
- Bake-off thật — `plans/260626-2329-dragdrop-ui-real-langchain-bakeoff/artifacts/bakeoff-verdict.json` (run `substrate-bakeoff-zl-real`, actor user:uspro): zerodep **1.0** vs langgraph **0.0** → winner zerodep (gap 1.0 > band 0.05).
- Gate chấm điểm — `drag_from_zero/dragzero/bakeoff/score.py`: `score = observability nếu inject_clean else 0.0`. `inject_clean` = inject agent giữa run + resume tới child-done **không recompile/restart**. Đây là năng lực domain runtime tồn tại để cung cấp (DEC-A4).
- Probes trung lập — `drag_from_zero/dragzero/bakeoff/port.py`: reconstruct_task_tree / detect_parked_task / attribute_action_to_agent / observe_roster_change_midrun. Cố ý không phát biểu theo "emits dragzero event X".

## 3 thứ này KHÁC loại — đừng gộp "đỡ xây lại"

| | Bản chất | Phán | Lý do |
|---|---|---|---|
| **LangFlow** | visual builder/platform có canvas riêng | LOẠI (DEC-11) | Sản phẩm cạnh tranh, không phải thư viện. Đã có canvas → lấy nó = vứt canvas + UI-lock + license. Là *đổi sản phẩm*, không phải đỡ việc. |
| **LangGraph** | runtime graph tĩnh (compile StateGraph) | KHÔNG làm spine | Thua bake-off 0.0 vs 1.0 đúng trên năng lực cốt lõi: inject giữa run + resume sạch. Graph tĩnh → đổi topology = recompile/restart. Trái thẳng luận đề `join_agent`→routable-ngay. |
| **LangChain** | thư viện integration (LLM/retriever/tool/parser) | Không cần | Không phải runtime, không thay được spine. Chỗ duy nhất nó đỡ việc = plumbing ngoại vi — đã build mỏng (`OpenAICompatLLM` ~270 dòng stdlib + JSON-repair ladder). Thêm = kéo dep nặng thay thứ đã xong. YAGNI. |

## Verdict

- **Substrate/runtime: KHÔNG adopt.** Đã quyết (DEC-11) + chứng minh bằng số (zerodep thắng tuyệt đối ở inject_clean). Không relitigate.
- Tiền đề "đỡ phải xây lại từ đầu" **gần như moot**: spine đã xong + xanh (304 tests). Phần mấy framework giúp (integrations) đúng là phần rẻ đã làm mỏng.
- Burr là path "rent" duy nhất từng cân nhắc nghiêm túc (FSM runtime, D2-prime) — không phải LangChain/Graph/Flow; và là trục riêng, ngoài câu hỏi này.

## Điều kiện DUY NHẤT để mở lại

Yêu cầu đổi bản chất: "cần hàng chục integration bên thứ ba thật nhanh" → cân LangChain *chỉ ở tầng tool/adapter*, không đụng spine; hoặc "multi-user cloud platform có sẵn" → đó là sản phẩm khác với luận đề single-user-local, lúc đó mới cân platform. Hiện tại: không.

## Câu hỏi mở

- Burr build-vs-rent (D1 vs D2-prime) vẫn chưa thấy verdict trong bake-off `zl` (chỉ zerodep+langgraph). Nếu còn treo → spike Burr riêng, không liên quan 3 tool đã hỏi.
