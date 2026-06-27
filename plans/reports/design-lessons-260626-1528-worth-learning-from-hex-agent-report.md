---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Notes: những gì đáng học từ hex_agent (cho thiết kế mới)

> Bối cảnh: bỏ codebase hex_agent, làm thiết kế mới hoàn toàn cho agent local-35B "decompose-until-trivial" (Navigator = code, Worker = 35B, theo `plans/260626-1221-recursive-decompose-agent/spec.md`). Doc này chốt lại các nguyên lý đáng mang theo, kèm bằng chứng file:line, và nói thẳng cái gì phải bỏ lại.
>
> Cách rút: 9 agent (7 thợ đào theo subsystem → 1 dao mổ YAGNI → 1 tổng hợp). Mọi file:line bên dưới là bằng chứng thật trong repo.

## Tinh thần (một câu)

Cả thiết kế chỉ là một luật áp khắp nơi: **model ĐỀ XUẤT (action, cấu trúc con, đo cái gì), code TRỌNG TÀI (PASS/FAIL đối chiếu với đĩa)**. Ranh giới toàn vẹn là *cấu trúc*, không phải lời hứa. hex_agent là bằng chứng đã chạy cho ba kỷ luật cần mang theo (tách claim khỏi verdict; biến termination thành định lý do code sở hữu; giam thế giới của model yếu). Nhưng ~70% LOC của nó (control plane, roles/skills/delegation, langgraph onion, freeze in-memory, thread-safety) sinh ra để phục vụ multi-tenant / real-time-UI / nhiều principal mà target local một-tiến-trình KHÔNG có và KHÔNG được kế thừa. Mang theo nguyên lý, bỏ lại framework.

## 6 chủ đề xuyên suốt (cốt lõi cần học)

### 1. Tách CLAIM khỏi VERDICT, chỉ code mới phán
Model đề xuất claim + dẫn chứng; code tính và ghi PASS/FAIL. **Không tồn tại field verdict ở bất kỳ chỗ nào Worker ghi được** → mất luôn đòn bẩy gian lận (prose không có `check` key để gọi tên thì không "ép thành pass" được).
- `supervisor/graph.py:231-256` — judge tự tái suy ra status; claim "passed" bị hạ về "pending" trừ khi evidence resolve được VÀ đúng type.
- `supervisor/evidence.py:16-40` — acceptance theo-type: scaffolding tự-sinh (plan, briefing, journal) là tập NON_EVIDENCE, bị từ chối kể cả khi được cite.
- `discipline/finish_gate.py:15-22` — "done" là *yêu cầu*, không phải verdict; "error" finish route sang fail, không giả dạng success.
- `toolbox/lint_test.py` — check KHÔNG chạy được (thiếu binary) phải là FAIL/error, không được im lặng pass.
- `control/events.py:134-151` — validate trong `__post_init__` → node sai cấu trúc *không thể* lọt vào tree.yaml. Luật thành cấu trúc, không phải khẩu hiệu.

### 2. Termination là định lý do code sở hữu, kèm backstop độc lập với measure
- mu lex-descent (chính) + per-root step budget (chặn cuối, lỏng hơn mu một cách có chủ đích) + detector non-progress (D4/D5 so chữ ký). Hai bộ dừng, không cái nào tin model. `spec.md:29,152,172`.
- **Leaf-ness phát hiện bằng thử K lần, không hỏi model** (`spec.md:28`) — lý do cốt lõi khiến kiến trúc *kiểm chứng được*.
- `supervisor/loop.py:154-199` — guard cơ học độc lập model (max-rounds, progress delta, decision-signature repeat, parse-errors đếm riêng) = bằng chứng đã chạy của convergence formalize trong spec.
- `discipline/budget.py:56-67` — same-tool-repeat key trên (tool + canonical-JSON args); tái dụng thành bộ đếm identical-propose mỗi node để *kích hoạt decompose* (leaf chưa trivial), không phải để giết loop.

### 3. Giam thế giới của model yếu: context bé cố định + parse khoan dung
- 4-cell context, đúng hai call type, không bao giờ thấy graph (`spec.md:38-42`).
- Thang sửa JSON deterministic-first, raw-candidate-thắng, mỗi nấc là `str->str` thuần nuốt exception của chính nó (`json_gate.py:1-7,305-370`).
- Chuẩn hóa SHAPE của action *sau* parse, *trước* dispatch — sửa JSON hợp-lệ-nhưng-không-dispatch-được; giữ tập coercion NHỎ, theo bằng chứng thật (`json_gate.py:420-432`).
- Re-prompt bằng skeleton cụ thể theo từng call type để copy nguyên văn, không phải lời dặn trừu tượng; không tốn step tiến độ (`json_gate.py:483-493`).
- Condense kết quả lớn đệ quy, có dấu cắt `+N` nhìn thấy được, trước khi quay lại context (`condense.py:7-24`).
- DeterministicBroker: briefing vừa-đủ từ slice được trao, có budget ký tự cứng + provenance → build/test bộ ráp 4-cell với ZERO LLM call trước (`supervisor/broker.py:31-55`).

### 4. Một chokepoint cho mỗi lớp effect: ép bằng topology, không bằng kỷ luật
- Mọi effect đi qua một hàm để cross-cutting (scope, lineage, normalize, cô lập crash) gắn ở *một* thân hàm mà call site mới không thể quên (`core/kernel.py:106-225`, `control/emitter.py:53-61`).
- Một `log_event()`/`write_verdict()` đóng dấu seq tăng dần per-root trước khi append; không node-handler nào tự append.
- Effect không bao giờ làm sập core: bọc call Worker + mọi gate-check trong try/except trả FAIL verdict (kèm text exception làm evidence) thay vì abort `solve()` (`kernel.py:156-157`, `events.py:27-31`). Nhưng KHÔNG được im lặng nuốt một gate FAIL — chỉ nuốt side-effect thuần phụ trợ.

### 5. Đĩa là nguồn sự thật duy nhất: idempotent nhờ content-addressing + commit nguyên tử + reader khoan dung
- tree.yaml + journal CHÍNH LÀ Blackboard: chỉ primitives, ghi sau mỗi transition, resume = đọc lại + bỏ qua done/decomposed, có identity-guard (`supervisor/state.py`, `loop.py:127-132`).
- Decomposition content-addressed two-phase-commit cho resume an-toàn-khi-crash miễn phí (`spec.md:32,206-225`): `decomp_id=sha256(id‖canonical_spec‖decomposer_version)`, temp-0, write+fsync staging rồi atomic flip.
- Mọi hiển thị status là *fold thuần* trên log bền: verdict terminal không bị ghi đè (`control/snapshot.py:231-233`).
- JSONL ledger append-only + seq tăng dần + reader chịu được corruption (bỏ dòng đuôi cụt/non-dict) + summary ghi-một-lần + guard run_id trong path (`observability/event_log.py:60-99`). BỎ RLock/_INDEX_LOCK và bảng metric — một dòng `{node_id, verdict, mu, ts}` là đủ.
- Reject-unknown ở biên bằng `frozenset`/`enum` Python cho CHECK_VOCAB, KHÔNG phải YAML loader+parser+registry; fail-loud khi gặp check key lạ. Đừng bao giờ `importlib` chuỗi module tùy ý (rủi ro supply-chain + tầng gián tiếp target local không cần).

### 6. Khớp trust boundary với threat thật: một principal, một LLM không tin được
- Toàn bộ bộ máy multi-actor (authz/attribution, role→allowlist, capability scope per-agent, delegation policy, redaction) gói lại thành đúng một luật spec đã nói: **worker không bao giờ ghi verdict, không resolve path, không mutate tree.**
- Port ý "thu hẹp đơn điệu" từ subset-scope sang *measure hội tụ*: `mu(child) < mu(parent)` ép lúc accept decomposition, đúng chỗ `scope<=parent` đang được ép (`delegation/policy.py:25-32`). BỎ capability-set per-node.
- Compose là reduce node thật (parent DONE iff reduce DONE); COMPOSE_FAIL (con done hết nhưng parent gate fail) là bug WIRING → freeze và surface, KHÔNG re-decompose (`spec.md:31,174`). Chẻ thêm không sửa được lỗi dataflow.
- Chỉ vớt progressive disclosure: lộ full check params của node khi nó ACTIVE, không phải cả cây — một mẹo tiết kiệm context-budget rẻ (`skills/registry.py:57-76`).

## Checklist must-carry (xếp theo độ "chịu lực", cao nhất trước)

| # | Bài học | Verdict | Bằng chứng | Áp dụng |
|---|---|---|---|---|
| 1 | Không có field verdict model ghi được; code là trọng tài duy nhất | keep | `supervisor/graph.py:231-256`; `spec.md:46,110-116` | Schema node KHÔNG có passed/status/score ở đâu Worker chạm được; chỉ `Navigator.run_checks` ghi PASS/FAIL. Invariant cứng. |
| 2 | 4-cell context + code-sở-hữu-global / 35B-đề-xuất-local | keep | `spec.md:42,38-40,45-47,30` | Chặn cứng prompt Worker còn 4 cell + 2 signature; `resolve_inputs()` ở code phát path tuyệt đối; Navigator là actor có-state DUY NHẤT. |
| 3 | Termination = định lý: mu lex-descent + step-budget backstop | keep | `spec.md:29,133,172,176`; `supervisor/loop.py:154-199` | `accept_decomposition` reject child không `lex_lt(mu(child),mu(parent))`; bộ đếm step per-root chặn cứng bất kể mu. Giữ cả hai. |
| 4 | Thang sửa JSON deterministic-first, raw thắng, sửa-mạnh-nhất-cuối | keep | `json_gate.py:1-7,305-317,346-394` | Parse CẢ hai call type qua thang này trước mọi schema-check. Đòn bẩy cao nhất; port gần nguyên văn. |
| 5 | Tách parse-error budget khỏi progress budget; gate trên *streak liên tiếp* | keep | `discipline/budget.py:11-25,37-54` | Hai bộ đếm độc lập: retry propose/decompose (JSON hỏng, gate theo streak, không tiến) vs step budget per-root. JSON fumble KHÔNG được trừ step budget. |
| 6 | Leaf-ness phát hiện bằng thử K lần, không hỏi model | keep | `spec.md:28,191-201` | Navigator không gọi `should_i_split()`; thử leaf K lần, đếm FAIL, chẻ theo đếm. Từ chối mọi shortcut "để model ước lượng độ khó". |
| 7 | No artifact = FAIL: bắt buộc, path-jail, non-empty, FRESH (mtime≥activated_at), check TRƯỚC khi chạy | keep | `spec.md:48,110,191` | Đóng dấu `activated_at` lúc activate(); `run_checks` loại missing/empty/ngoài-jail/cũ-hơn-activated_at trước khi eval predicate. |
| 8 | done_when = triple typed; accept-decomposition là gate cấu trúc thuần TRƯỚC khi mutate cây | keep | `spec.md:91,93-108,118-150` | done_when là enum đóng các check, KHÔNG verdict field; thêm check chỉ ở code. `accept_decomposition` là một hàm reason-list thuần; chưa Accept thì chưa chạm cây. |
| 9 | Đĩa là nguồn sự thật: decomposition content-addressed + two-phase-commit, projection là fold thuần | keep | `spec.md:32,206-225`; `supervisor/state.py`, `loop.py:127-132` | Hash (id, canonical_spec, decomposer_version) → decomp_id; temp-0; persist con content-addressed; atomic flip; resume cache-hit trả nguyên văn. Crash-safety miễn phí. |
| 10 | Validate invariant trong `__post_init__` → record sai không thể tồn tại | keep | `control/events.py:134-151`; `checkpoint.py:38-51` | Record trên đĩa là frozen dataclass validate lúc dựng: done_when phải là triple {check,params,artifact}, check ∈ vocab đóng, KHÔNG verdict/status/score. Giữ field set nhỏ. |
| 11 | Chuẩn hóa SHAPE action + condense + re-prompt skeleton | simplify | `json_gate.py:420-432,483-493`; `condense.py:7-24` | Giữ shape-normalizer (coercion NHỎ, theo bằng chứng), condense nguyên văn (gọi inline, bỏ wrapper middleware), skeleton re-prompt theo call-type không re-dump 4-cell. |
| 12 | Một chokepoint mỗi lớp effect, nhưng INLINE chứ không dựng onion pluggable | simplify | `core/kernel.py:106-225`; `control/emitter.py:53-61` | Một `run_action()/run_gate()/write_verdict()/log_event()`. BỎ `kernel.use(mw)` onion, latch, fail_open flag. Gates fail-CLOSED; telemetry fail-OPEN. |
| 13 | Exec argv no-shell + path-jail fail-closed (an toàn tool duy nhất target cần) | simplify | `toolbox/terminal.py:32-43`, `lint_test.py:60-91`; `safety/sandbox.py:25-56` | Check `test_passes`/`cmd_*` chạy qua cmd_id whitelist → argv cố định (KHÔNG raw shell từ 35B), cwd, timeout. Mọi path qua resolve-under-root + `is_relative_to`. BỎ SafeToolPort + profile per-agent. |
| 14 | Build vertical slice leaf-attempt TRƯỚC; hoãn DAG/reduce/decompose/cache | keep | `spec.md:331-341` | Ship đúng 5 bước slice; tự cấm thêm cache content-addressed / two-phase commit / D4-D5 cho tới khi loop leaf-attempt + DFS closure pass trên cây RAG hand-baked. |

## Anti-bài-học: bỏ lại (≈70% LOC)

- **Toàn bộ `control/` (~1566 LOC):** RuntimeEvent envelope, event/command YAML registries, RuntimeCheckpoint risk-tier, redaction (raw vs ui_payload), replay ring buffer + needs_resync + Last-Event-ID, authz/attribution. *Vì:* tất cả phục vụ multi-tenant + real-time-UI + consumer remote reconnect. Target có MỘT user, MỘT process, tree-trên-đĩa là sự thật. Giữ lại chỉ kỷ luật trừu tượng (một publish chokepoint, log có thứ tự append-only, vocab đóng dạng enum, validate-trong-`__post_init__`, projection-là-fold). Redaction/replay/authz: bỏ hẳn.
- **`roles/` + `skills/` + `delegation/` như hệ authority/identity:** RoleSpec, Agent, Lens, role→allowlist (forbidden-wins), capability profile per-agent, DelegationPolicy, PolicyEngine.validate. *Vì:* permission đa-persona đa-actor cho một worker mà spec định nghĩa là proposer không-state không-identity. Vớt CHỈ invariant thu-hẹp-đơn-điệu (viết lại thành `mu(child)<mu(parent)`) + progressive disclosure.
- **Coupling langgraph + cả onion `graph/`+`middleware/`:** StateGraph/InMemorySaver, conditional_edges, protocol whole-state-per-patch, số học `recursion_limit`, `kernel.use(mw)` onion, `_LatchedNext`, fail_open flag, lớp class AgentKernel/KernelSession, Protocols+NullToolPort+YAML bootstrap. *Vì:* đây là thứ lớn nhất KHÔNG nên kế thừa. DFS tuần tự một-process trên cây là call stack thuần + cursor tree.yaml: đúng một implementation mỗi seam, một thứ tự gate cố định, không middleware bên thứ ba để phòng, không trần engine để hòa giải. GIỮ route-as-a-state-field + node-as-fn(state)->patch; BỎ engine đã đẻ ra chúng.
- **State frozen in-memory:** `core/state.py` StateStore, `freeze()`/`_deep_freeze`/MappingProxyType, deepcopy snapshot/restore, KernelSession. *Vì:* để chặn run đồng thời trong-process làm hỏng nhau + snapshot RAM. Target persist TẤT CẢ ra file; resume từ đọc-lại-đĩa. Nguyên lý immutability sống (config/vocab/decomposer_version cố định per root); bộ máy thì không.
- **Phòng thủ thread-safety/concurrency:** RLock, _INDEX_LOCK, SessionSeq, test 2000-event. *Vì:* agent một-process một-cursor không có writer đồng thời. Lock + ma trận test concurrency giải bài toán không tồn tại, thêm bug eviction/ordering đổi lấy số 0.
- **Default-OFF cho gate AN TOÀN:** hex_agent để policy gate + budget guard opt-in (`bootstrap.py:39,43`). *Vì:* đúng cho config FEATURE tùy chọn (áp "absent = inert" cho field node tùy chọn: depends_on/inputs/notes mặc định rỗng). Nhưng ĐẢO cho an toàn: artifact-jail, mu-decrease, step-budget backstop phải LUÔN-BẬT, không tùy chọn. Thiếu field mu/budget phải HARD-FAIL, không default im lặng.
- **Kéo cache content-addressed / two-phase commit / D4-D5 lên slice đầu.** *Vì:* chúng chỉ có nghĩa khi `decompose()` tồn tại; build sớm = code không-có-caller, không test được. Spec cố ý xếp chúng cuối (`spec.md:341`).

## Rủi ro mở phải chốt TRƯỚC khi code (từ `spec.md` §open-questions)

- **`scope_token_len` normalize:** tokenizer drift qua `decomposer_version` làm tiebreak của mu không so được → phá ngầm termination proof. Khuyến nghị: bỏ tiebreak token, dùng `done_when_count` làm measure DUY NHẤT (well-order sạch; tie hiếm thì step-budget backstop lo).
- **`criteria_coverage`:** partition chính xác hay superset? Khuyến nghị: định nghĩa coverage = "mỗi criterion của parent được ≥1 child *kéo theo*" (superset-implication), không phải set-equality.
- **`weaker_than_ancestor`:** cần partial order trên các check, chưa định nghĩa *ngang kind* (range vs grep). Không có order thì luật "không nới metric" không enforce được ngang kind.
- **`reduce_op: worker` budget:** reduce do worker tự decompose được → chia step budget của parent (đói leaf) hay cho budget riêng (compose vô hạn)?
- **`needs` (cross-tree) vs `depends_on` (in-subtree) acyclic dưới decomposition SỐNG:** child mới có thể thêm `needs` đóng vòng *giữa run*, sau khi topo-check lúc load đã pass. PHẢI chạy lại cycle-check trên MỌI decomposition sống thêm `needs` edge.
- **K tuning:** K=3 phẳng hay scale theo `done_when_count`?
- **Human-in-the-loop trong run local không người trông:** BLOCKED luôn terminal, hay có degraded auto-mode (nới done_when *yếu nhất*, log, đi tiếp)? Khuyến nghị: chọn degraded auto-mode để run local không treo mãi ở BLOCKED đầu tiên.

## Bước đầu tiên (slice dọc, theo `spec.md:331-341`)
1. Loader tree.yaml + referential-integrity + path-jail lúc load (code).
2. Gate-1 runner 4 check thôi (`file_exists`, `json_field_in_range`, `grep_absent`, `all_children_done`); verdict do code ghi; no-artifact=FAIL.
3. `solve()` chỉ nhánh leaf-attempt: activate → propose → run → run_checks → DONE | retry-K | BLOCKED(UNSOLVABLE_LEAF). Journal mỗi attempt.
4. Một cây 2-tầng hand-baked (RAG eval) để DFS/`all_children_done` chạy mà không cần `decompose()`.
5. Per-root step budget = backstop duy nhất.

Chứng minh: ráp 4-cell, gate là trọng tài duy nhất, no-artifact=FAIL, DFS cursor + parent-done-theo-con. RỒI mới thêm Gate-2 + `decompose()`, RỒI `inputs/outputs`+reduce, RỒI D4/D5 + cache content-addressed.
