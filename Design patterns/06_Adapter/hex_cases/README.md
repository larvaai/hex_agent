# Adapter trong hex_agent — Hồ sơ thực chiến (hex_cases)

> **Adapter = chuyển interface của một class sang interface mà client kỳ vọng, để hai bên
> không tương thích vẫn hợp tác được.** (theo bài học gốc `../06_Adapter.md`)

Thư mục này chưng cất pattern **Adapter (Structural)** *như nó thực sự xuất hiện* trong
codebase `hex_agent`, không phải ví dụ tưởng tượng. Mỗi case con là một bản rút gọn chạy
được bằng **thư viện chuẩn Python** (không import hex_agent, không third-party), kèm README
trỏ thẳng tới `path:line` thật để bạn đối chiếu.

---

## Vì sao hex_agent đầy Adapter?

hex_agent theo **kiến trúc hexagonal (ports & adapters)**. Domain core (RagService, vòng lặp
agent, bộ điều phối delegation) chỉ phụ thuộc vào các **port** (Protocol do domain sở hữu).
Mọi thứ "bẩn" bên ngoài — Qdrant qua mạng, server LLM kiểu-OpenAI, fastembed, langgraph,
filesystem, subprocess — đều bị nhốt sau một **concrete adapter** cài đặt port đó.

Hệ quả nhìn thấy được:
- **Thay backend không sửa core**: đổi `InMemoryVectorStore ↔ QdrantVectorStore` chỉ là đổi
  đối tượng truyền vào `RagService(...)`. Code service y hệt.
- **Test nhanh, tất định**: mỗi port thật có một adapter giả (`FakeEmbedder`,
  `ScriptedDelegationAgent`, `RecordedLLM`) chạy cục bộ, không cần mạng/LLM/Docker.
- **Anti-corruption layer**: API third-party hay đổi hoặc hay hỏng được dịch về một hợp đồng
  nội bộ ổn định (vd `call_llm()` luôn trả JSON, không bao giờ raise).

Đa số là **Object Adapter** (composition: adapter giữ adaptee qua một field như `_client`,
`_chunks`, `artifacts`, graph), đúng như bài học gốc khẳng định Object Adapter là default
trong Python hiện đại.

---

## Các case con

| Case | Thư mục | Nội dung | path:line gốc |
|------|---------|----------|---------------|
| **01** | [`01_rag_vector_store_adapter/`](./01_rag_vector_store_adapter/) | Hai vector store (in-memory + Qdrant) sau cùng một `VectorStorePort`; chứng minh substitutability + health-gate khi server chết. | `rag/ports.py:31-36`, `rag/stores.py:24-57`, `rag/stores_qdrant.py:32-148`, `rag/service.py:15-113` |
| **02** | [`02_llm_openai_adapter/`](./02_llm_openai_adapter/) | Adapter bọc client LLM kiểu-OpenAI: retry/backoff, downgrade json→text, dịch mọi lỗi thành envelope JSON actionable (không raise). | `llm/adapter.py:25-119`, `tests/test_llm_adapter.py:54-82` |
| **03** | [`03_delegation_agent_adapters/`](./03_delegation_agent_adapters/) | Hai delegation agent (Scripted tất định + LangGraph streaming) sau cùng một `DelegationPort`. | `core/ports.py:32-45`, `adapters/agents/scripted.py:17-59`, `adapters/agents/langgraph_agent.py:21-95` |

Bảng **vét cạn mọi occurrence** (kể cả các adapter nhỏ như `FastEmbedEmbedder`,
`OpenAICompatLLM`, `RecordedLLM`, các filesystem tool, và các ví dụ dạy học) nằm ở
[`CATALOG.md`](./CATALOG.md).

---

## Chạy thử

```bash
python3 01_rag_vector_store_adapter/rag_vector_store_adapter.py
python3 02_llm_openai_adapter/llm_openai_adapter.py
python3 03_delegation_agent_adapters/delegation_agent_adapters.py
```

Mỗi file in narration tiếng Việt từng bước, có `assert` chứng minh bất biến của pattern, và
một đối chứng "khi KHÔNG dùng Adapter thì khó/hỏng thế nào". Tất cả thoát code 0, không
traceback.

---

## Nhắc lại tinh thần (từ bài học gốc)

- Adapter chỉ **dịch interface, không thêm logic nghiệp vụ**. Nếu adapter làm tính toán phức
  tạp / che cả hệ con → có thể đã là Facade hoặc Decorator, không còn là Adapter.
- Dấu hiệu cần Adapter: tích hợp third-party/legacy có API khác; cùng concept có nhiều biểu
  diễn; cần anti-corruption layer; đang có `if/else` dài check source/format.
- Cặp kết hợp hay gặp ở đây: **Adapter + Strategy** (nhiều adapter cho nhiều backend, runtime
  chọn) và **Adapter + Factory** (factory dựng adapter theo cấu hình, vd `backend: qdrant`).
