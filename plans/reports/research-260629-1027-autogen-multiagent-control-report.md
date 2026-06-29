---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Nghiên cứu: cách microsoft/autogen điều khiển multi-agent

- Ngày: 2026-06-29 10:27 +07
- Phương pháp: research fan-out 4 mặt + verify đối kháng nguồn sơ cấp (9 agent, 354k tok). Mọi mặt verdict **SOLID**; có refute + correction thật (ghi ở §Đính chính).
- Mục đích: dạy 2 cơ chế điều khiển (message-passing/actor; group-chat-manager + termination), CHÍNH XÁC theo phiên bản.

---

## Cảnh báo phiên bản (đọc trước, nếu không sẽ học nhầm API đã chết)

autogen có **hai thế hệ, cùng repo, API không tương thích**:

- **v0.2** — pip `pyautogen~=0.2.0`, import `autogen`. Hội thoại-centric, **đồng bộ**: `ConversableAgent` + `GroupChat` + `GroupChatManager` + `initiate_chat`. Docs: `microsoft.github.io/autogen/0.2/`.
- **v0.4+** — GA **17/01/2025**, viết lại từ đầu, **3 package**: `autogen-core` (actor runtime **async**) + `autogen-agentchat` (teams) + `autogen-ext` (model clients, vd `OpenAIChatCompletionClient`).
- **Hiện trạng (~2026):** README chính thức ghi *"AutoGen is now in maintenance mode... community managed"* (chỉ bug/security/docs, **không feature mới**). Successor: **Microsoft Agent Framework (MAF)** — hợp nhất AutoGen + Semantic Kernel, 1.0 GA đầu tháng 4/2026 (blog đề 03/04/2026).
- **Bẫy tên chí mạng:** `AssistantAgent` và `UserProxyAgent` là **hai tên duy nhất sống sót** qua ranh giới — nhưng là class **async MỚI**. Phân biệt bằng **import path**: `from autogen import ...` = v0.2; `from autogen_agentchat.agents import ...` = v0.4. **Không có `ConversableAgent` ở v0.4** (base là `BaseChatAgent`).

---

## 1. Message-passing / Actor Model (v0.4 `autogen-core`)

`autogen-core` = *"a scalable, event-driven actor framework"* (launch blog). Đặc tính định nghĩa **Actor Model**: agent **KHÔNG do code ứng dụng tạo/sở hữu** — **runtime** sở hữu vòng đời + giao message. Docs (`agent-and-agent-runtime.html`): *"Agents are not directly instantiated and managed by application code. Instead, they are created by the runtime when needed."*

- Runtime cục bộ: `SingleThreadedAgentRuntime` (còn có runtime gRPC phân tán).
- Đăng ký bằng factory: `BaseAgent.register(runtime, "my_agent", lambda: MyAgent())`; runtime **lazy** tạo instance lần đầu có message gửi tới `AgentId` đó.
- **Hai primitive giao tiếp** (tên API chính xác, từ source `_agent_runtime.py`):
  - `send_message(message, recipient: AgentId, ...)` — **TRỰC TIẾP**, request/response, point-to-point.
  - `publish_message(message, topic_id: TopicId, ...)` — **BROADCAST / pub-sub**. Subscriber resolve từ `TopicId` qua `TypeSubscription`.
- Routing trong agent: base class `RoutedAgent(BaseAgent)`; handler gắn `@message_handler` (`def message_handler(func=None, *, strict=True, match=...)`) — route theo **kiểu message**, có `match` tùy chọn. Source: `_routed_agent.py`.

**Điểm KHÔNG được lẫn:** routing v0.4 là **runtime làm trung gian** (`AgentId` cho trực tiếp; `TopicId`+`TypeSubscription` cho pub-sub) — **KHÔNG phải** "một manager quyết ai nói tiếp". Cái "manager quyết ai nói" là cơ chế **v0.2** (`GroupChatManager.select_speaker`), xem §2.

---

## 2. Group Chat Manager — "ai được nói tiếp?"

Khái niệm: trong "group chat" nhiều agent, sau mỗi lượt một **manager** quyết agent nào nói tiếp. Khác hẳn routing của actor runtime.

### v0.2 (`pyautogen`)
`GroupChat` giữ participants + lịch sử, expose `select_speaker(last_speaker, selector)`. `GroupChatManager` (subclass `ConversableAgent`) điều phối: mọi agent gửi cho manager → manager chọn người kế → broadcast → lặp. Khởi động bằng `initiate_chat`. Chính sách = arg `speaker_selection_method` ∈ `{"auto"(LLM, mặc định), "manual", "random", "round_robin"}` hoặc `Callable[[last_speaker, groupchat], Agent|str|None]` — trả `None` thì **DỪNG** hội thoại. `"auto"`: prompt role-play cho LLM, parse tên; parse hỏng thì re-query tới `max_retries_for_selecting_speaker` (mặc định **2**). `allow_repeat_speaker` mặc định **True**.

### v0.4+ (`autogen-agentchat` teams)
`GroupChatManager` công khai **biến mất**; mỗi team subclass `BaseGroupChat` với một **manager actor nội bộ**, chạy `team.run()` / `team.run_stream()`. **Bốn chiến lược**:
- `RoundRobinGroupChat` — xoay vòng cố định, **không gọi LLM**.
- `SelectorGroupChat` — **LLM chọn** người kế (analog trực tiếp của `"auto"` v0.2).
- `Swarm` — chọn theo `HandoffMessage.target` cuối cùng (worker tự bàn giao).
- `MagenticOneGroupChat` — Orchestrator + **Task Ledger** (facts/plan) + **Progress Ledger**; re-plan khi kẹt.

### Thuật toán `SelectorGroupChat` chính xác (verify với source `_selector_group_chat.py`)
1. Nếu có `selector_func` và trả non-None → agent đó nói (BỎ QUA LLM).
2. Dựng candidate: mặc định = mọi participant; nếu `allow_repeated_speaker=False` (**mặc định False** — ngược v0.2) và có previous speaker → loại nó; nếu có `candidate_func` → nó trả list candidate, **ghi đè** bộ lọc repeat.
3. Render `selector_prompt` (mặc định role-play: `"You are in a role play game. The following roles are available:\n{roles}.\nRead the following conversation. Then select the next role from {participants} to play. Only return the role.\n\n{history}\n\n..."`).
4. Parse reply bằng `_mentioned_agents`, regex/tên: `r"(?<=\W)(" + re.escape(name) + "|" + re.escape(name.replace('_',' ')) + "|" + re.escape(name.replace('_', r'\_')) + r")(?=\W)"` — biên từ, dung sai underscore/space.
5. Resolve: đúng 1 match → nói; 0 match → re-query `"No valid name was mentioned..."`; >1 → `"Expected exactly one name to be mentioned..."`; chọn lại previous khi cấm repeat → `"Repeated speaker is not allowed, please select a different name from: {...}."`
6. Retry tới `max_selector_attempts` (**mặc định 3**); cạn thì fallback previous speaker, không có thì `participants[0]`.

`Swarm` (source `_swarm_group_chat.py`): khởi tạo current = `participants[0]`; quét thread ngược tìm `HandoffMessage` cuối → next = `.target`; không có thì giữ nguyên; `validate_group_state` raise `ValueError` nếu target không thuộc participants.

---

## 3. Termination — "khi nào dừng?"

### v0.4+ (mô hình tổng quát hóa)
Base trừu tượng `TerminationCondition` trong `autogen_agentchat.base` (source `_termination.py`). Là callable: `async __call__(messages: Sequence[BaseAgentEvent | BaseChatMessage]) -> StopMessage | None`. **Ngữ nghĩa then chốt** (verbatim từ docstring): nó nhận **chỉ message từ lần gọi trước tới giờ — DELTA mỗi lượt, không phải toàn lịch sử**. Trả `StopMessage` = dừng, `None` = tiếp. Có property `terminated: bool` + `async reset()`.

Team (group-chat manager) sở hữu một condition, đánh giá sau mỗi lượt; khi cháy, `run()/run_stream()` trả `TaskResult` với `stop_reason: str | None` (vd `"Maximum number of messages 3 reached"`).

**Compose** (thiết kế đáng học): `&` → `AndTerminationCondition` (cháy khi MỌI sub đã cháy, tích lũy StopMessage), `|` → `OrTerminationCondition` (cháy khi BẤT KỲ sub cháy).

**Stateful** (bất đối xứng đã verify verbatim): condition đã cháy → `terminated==True`, gọi lại sẽ **raise** tới khi `reset()`. `OrTerminationCondition` raise `RuntimeError("Termination condition has already been reached")` (KHÔNG dấu chấm cuối); `AndTerminationCondition` raise `TerminatedException("Termination condition has already been reached.")` (CÓ dấu chấm). Team auto-reset sau mỗi run.

**11 built-in** (verbatim từ stable conditions reference): `MaxMessageTermination(max_messages, include_agent_event=False)` · `TextMentionTermination(text, sources=None)` · `StopMessageTermination()` · `TokenUsageTermination(max_total_token, max_prompt_token, max_completion_token)` · `HandoffTermination(target)` · `TimeoutTermination(timeout_seconds)` · `ExternalTermination()` [app gọi `set()` để dừng lượt kế] · `SourceMatchTermination(sources)` · `TextMessageTermination(source=None)` · `FunctionCallTermination(function_name)` · `FunctionalTermination(func)` [predicate người dùng trên delta].

### v0.2 (rải rác, tiền nhiệm)
Không có object condition thống nhất. Dừng bằng `GroupChat(max_round=...)` + `is_termination_msg` mỗi agent (vd `lambda msg: "TERMINATE" in msg["content"]`) + `max_consecutive_auto_reply`, check trong `ConversableAgent/GroupChatManager` lúc `initiate_chat`. (Lưu ý: loop 2-agent còn có `max_turns` của `initiate_chat` — KHÁC `GroupChat.max_round`.)

---

## Bảng LEGACY (v0.2) ↔ CURRENT (v0.4+)

| Khái niệm | v0.2 (LEGACY) | v0.4+ (CURRENT) |
|---|---|---|
| Package / import | `pyautogen` / `import autogen` | `autogen-core`+`autogen-agentchat`+`autogen-ext` |
| Base agent | `ConversableAgent` (`register_reply`) | `BaseChatAgent` (không có ConversableAgent) |
| Bắt đầu chat | `agent.initiate_chat(...)` | `team.run()/run_stream()`; `agent.on_messages()` |
| Container multi-agent | `GroupChat` | `RoundRobinGroupChat` / `SelectorGroupChat` |
| Driver | `GroupChatManager` | (gộp vào team, không manager riêng) |
| Khi nào dừng | `max_round` + `is_termination_msg` | `TerminationCondition` compose `&`/`|` |
| Model config | dict `llm_config` | `OpenAIChatCompletionClient` (autogen-ext) |
| Ai nói tiếp | `GroupChat.select_speaker` | manager actor nội bộ / `selector_func` |

---

## Đính chính (verify bắt được — dùng bản này, KHÔNG dùng bản research thô)

- Broadcast API là **`publish_message()`** (source `_agent_runtime.py`), **KHÔNG** phải `publish()` (một docs page dùng "publish()" lỏng lẻo trong prose). Direct = `send_message()`. Cả hai **chỉ v0.4+**.
- **`streaming_selector_func` KHÔNG tồn tại** trên `SelectorGroupChat` (refute với source main).
- Param template v0.2 là `select_speaker_message_template` / `select_speaker_prompt_template` (+ `..._auto_multiple_template` / `..._auto_none_template`) — KHÔNG phải `select_speaker_msg/prompt`.
- **Spelling trap:** v0.2 `allow_repeat_speaker` (mặc định **True**) ≠ v0.4 `allow_repeated_speaker` (mặc định **False**). Khác cả chữ lẫn mặc định.
- Retry: v0.2 `max_retries_for_selecting_speaker`=2; v0.4 `max_selector_attempts`=3.
- `initiate_chat` cho **sequential-chat KHÔNG có thay thế 1:1** ở v0.4 — phải tự dựng trên Core API; chỉ group-chat map sạch sang `team.run()`.

## Nguồn sơ cấp
- `github.com/microsoft/autogen` (main README; source `_agent_runtime.py`, `_routed_agent.py`, `_selector_group_chat.py`, `_swarm_group_chat.py`, `_termination.py`)
- `microsoft.github.io/autogen/stable/` (reference: `autogen_agentchat.conditions`, `.base`, `.teams`; user-guide; migration-guide)
- `microsoft.github.io/autogen/0.2/` (reference groupchat, conversable_agent)
- `devblogs.microsoft.com/autogen/autogen-reimagined-launching-autogen-0-4/` (GA 17/01/2025)
- `github.com/microsoft/autogen/releases` (latest `python-v0.7.5`, 2025-09-30)
- `azure.microsoft.com/.../introducing-microsoft-agent-framework/` + `devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/` (MAF successor)

## Chưa chắc
- Ngày GA chính xác: blog render 17/01/2025; vài nguồn phụ ghi 14/01. Tháng thì chắc.
- Verbatim default `selector_prompt` lấy từ source main cho một tag; wording đã đổi qua các release.
