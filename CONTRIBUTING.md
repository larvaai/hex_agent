# Contributing to `core_agent`

Cảm ơn bạn muốn đóng góp. Repo này phát triển theo **Epic → acceptance criteria → test → code**;
đường tắt qua các runtime boundary thường tạo bug khó thấy ở checkpoint, scope hoặc observability.

Hướng dẫn đầy đủ cho người mới:
[Onboarding & Contributing](docs/ONBOARDING_AND_CONTRIBUTING.md).

## Setup nhanh

```powershell
git clone <repository-url>
cd myagent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Linux/macOS activation:

```bash
source .venv/bin/activate
```

Baseline trước khi sửa:

```powershell
python -m pytest
python -m ruff check .
python run_smoke.py
```

Default suite không cần API key/LLM/external service. Optional Qdrant integration tests được skip
khi dependency hoặc local server không sẵn sàng.

## Workflow

1. Đọc `README.md` → `docs/RUN_AND_CONFIGURE.md` → `MAP.md` → `docs/RUNTIME_FLOW.md`.
2. Tìm Epic/acceptance liên quan trong `docs/rebuild_from_zero/`.
3. Tạo branch nhỏ, chỉ giải quyết một mục tiêu.
4. Viết hoặc cập nhật test thể hiện behavior mong muốn.
5. Sửa code tại đúng boundary; không bypass session/kernel/delegation/safety.
6. Cập nhật docstring, tài liệu runtime/config và `CHANGELOG.md` nếu behavior đổi.
7. Chạy test trọng yếu, full suite, Ruff và smoke.

Commit convention đang được dùng:

```text
feat(E10): add durable worker checkpoint
fix(E06): reject workspace escape through symlink
test(E09): cover forbidden-tool precedence
docs: explain role and skill composition
```

## Definition of Done

- Behavior có test offline/deterministic.
- `python -m pytest`, `python -m ruff check .`, `python run_smoke.py` đều xanh.
- Không commit `var/`, log, secret, virtualenv hay runtime database.
- Tool mới có canonical name, descriptor `kind/idempotent/risk`, safety policy và envelope test.
- State mới serializable, có migration/codec nếu cần và có resume test.
- Public behavior/config/topology đổi thì docs tương ứng cũng đổi.
- Diff không chứa reformat hoặc thay đổi ngoài phạm vi.

## Boundary bắt buộc giữ

- Runtime scoped gọi tool qua `KernelSession.execute_tool()`, không gọi executor trực tiếp.
- LLM và tool đều đi qua `AgentKernel.execute_tool()`.
- Delegation đi qua `DelegationServicePort/DelegationManager`, không nhét vào kernel.
- Shared kernel/registry/config freeze trước session đầu tiên; mutable state thuộc session.
- `langgraph.sqlite` là parent resume truth; `checkpoint.json` chỉ là UI projection.
- `AgentState` và Supervisor Blackboard chỉ chứa dữ liệu encode được.
- Prompt không thay thế capability scope hoặc safety policy.

Trước khi sửa file lõi, đọc [Known Risks](docs/KNOWN_RISKS.md) và
[Code Review](docs/CODE_REVIEW.md).
