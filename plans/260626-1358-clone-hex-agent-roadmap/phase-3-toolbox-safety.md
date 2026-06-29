---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 3 — Toolbox, Safety jail & middleware

> Epic: E06 · Cổng vào: Phase 1 (kernel chokepoint) · Rời phase với: mọi tool đụng đĩa/subprocess đều đi qua **một cửa** (jail + policy + middleware xếp lớp), không tool nào tự do chạm hệ thống.

## 1. Mục tiêu & ranh giới

Phase 1 đã cho bạn một **chokepoint**: mọi capability vào qua `kernel.execute_tool`. Phase này nhồi vào chokepoint đó những thứ thực sự *nguy hiểm* — đọc/ghi file, chạy lệnh — và bọc chúng sao cho không bao giờ thoát khỏi tầm kiểm soát.

Ba lớp phòng thủ, từ trong ra ngoài:

1. **Workspace jail** (`safety/sandbox.py`): path nào cũng bị ép về trong `var/workspace`. Đây là lớp *vật lý* — không có cách diễn giải path nào đưa được ra ngoài.
2. **SafeToolPort + ToolPolicy** (`safety/policy.py`): mỗi tool toolbox bị bọc một lớp policy *trước khi* chạy — chặn shell, chặn lệnh huỷ diệt, chặn git mutation.
3. **Middleware chain** (`middleware/`): timing → policy(deny) → budget → retry → condense, cắt ngang *mọi* capability ở kernel.

**Ranh giới**: phase này KHÔNG dựng graph (Phase 4), KHÔNG dựng LLM (Phase 2). Nó chỉ trả lời một câu: *làm sao để một tool nguy hiểm trở nên an toàn-để-trao-cho-agent.*

## 2. Bạn sẽ xây gì (bản đồ module)

```
safety/
  sandbox.py     resolve_in_workspace()  — path-jail (I8)
  policy.py      SafeToolPort, ToolPolicy, classify_terminal — chokepoint policy (I9)
toolbox/
  feature.py     install(kernel): đăng ký tool, BỌC mỗi tool bằng SafeToolPort
  filesystem.py  FsRead/FsWrite/FsList + FsStrReplace/FsInsert/FsWriteLines (jailed)
  terminal.py    Terminal — argv (NO shell) + timeout
  lint_test.py   LintCompile/RuffCheck/PytestRun — argv cố định, không shell
  code_index.py  CodeIndex/FindSymbol/FindReferences/DependencyGraph — read-only
middleware/
  timing.py      TimingLog (fail-open)
  policy.py      PolicyGate (deny-list)
  budget.py      BudgetGuard (KHÔNG wire ở kernel)
  retry.py       Retry
  condense.py    CondenseResult (fail-open)
core/bootstrap.py  _install_middleware(): wire chain từ config (order = ngoài→trong)
```

Quan hệ then chốt: `toolbox/feature.py` là nơi **jail** (qua tool) và **policy** (qua `SafeToolPort`) gặp nhau; `core/bootstrap.py` là nơi **middleware** ráp vào kernel.

Đọc bản đồ theo *hướng kiểm soát* — mỗi module trả lời một câu "ai chặn cái gì":

| Module | Câu nó trả lời |
|---|---|
| `safety/sandbox.py` | "Path này có nằm trong workspace không?" → giam hoặc raise |
| `safety/policy.py` | "Tool+args này có được phép chạy không?" → cho qua hoặc `policy_blocked` |
| `toolbox/filesystem.py` | "Đọc/ghi file an toàn" — luôn jail trước, editor có count-guard |
| `toolbox/terminal.py` | "Chạy lệnh không-shell, có timeout" — argv list, không injection |
| `toolbox/lint_test.py` | "Validate code bằng argv cố định" — không nhận chuỗi lệnh từ model |
| `toolbox/code_index.py` | "Tra cứu symbol/ref read-only" — không hàm nào ghi |
| `middleware/*` | "Cắt ngang mọi capability" — đo, deny, retry, co kết quả |
| `core/bootstrap.py` | "Ráp tất cả vào kernel" theo đúng thứ tự ngoài→trong |

## 3. Dựng step-by-step

### Bước 1 — Workspace jail (`safety/sandbox.py`)

Hàm duy nhất quan trọng: `resolve_in_workspace()` (`safety/sandbox.py:46`). Logic: ép path tương đối về dưới `workspace`, `resolve()`, rồi kiểm `is_relative_to(workspace)`.

Điểm tinh tế: nó **từ chối lexically** path kiểu Windows *trước khi* resolve (`_reject_foreign_path_syntax`, `safety/sandbox.py:25`) — vì trên POSIX `..\escape` là tên file hợp lệ và `C:/x` là *relative*, nên `resolve()` sẽ vô tình giữ chúng *bên trong* workspace. Fail-closed up front.

**Tự kiểm**: `resolve_in_workspace("../../etc/passwd")` phải raise `SandboxError`. `resolve_in_workspace("sub/file.txt")` phải trả `var/workspace/sub/file.txt`.

### Bước 2 — SafeToolPort policy (`safety/policy.py`)

`SafeToolPort` (`safety/policy.py:105`) bọc một executor: gọi `ToolPolicy.check()` *trước*, nếu `not allowed` trả envelope `policy_blocked=True` và **không** chạm `inner`. Đây là chokepoint một-cửa: muốn thêm luật an toàn, sửa `ToolPolicy.check`, không rải khắp các tool.

`classify_terminal` (`safety/policy.py:53`) là bộ luật cho terminal: chặn shell exe, chặn token shell (`|`, `&&`, `$(`...), chặn `rm/dd/mkfs`, chặn git mutation (trừ khi bật env), chặn argv trỏ path tuyệt đối ngoài workspace.

**Tự kiểm**: `SafeToolPort("x", inner).execute(req)` với `terminal_run argv=["bash","-c","..."]` → `policy_blocked=True`, `inner` không được gọi.

### Bước 3 — Filesystem tools (`toolbox/filesystem.py`)

6 tool: `fs_read/fs_write/fs_list` + 3 editor phẫu thuật `fs_str_replace/fs_insert/fs_write_lines`. **Mỗi** tool gọi `resolve_in_workspace(...)` đầu tiên (vd `FsRead.execute`, `filesystem.py:21`), bắt `SandboxError` thành envelope `ok=False`.

`FsStrReplace` (`filesystem.py:77`) còn *đếm* số lần khớp: nếu `found != expected` thì **từ chối** sửa (tránh thay đổi mơ hồ/quá rộng) — đây là editor có guard, không phải replace mù.

**Tự kiểm**: `fs_write path="/etc/x"` → `ok=False`, không file nào bị tạo ngoài workspace.

### Bước 4 — Terminal (no-shell + timeout) (`toolbox/terminal.py`)

`Terminal.execute` (`terminal.py:15`): nhận `argv` *là list*, chạy `subprocess.run([...], cwd=workspace, timeout=...)` — **không** `shell=True`, **không** chuỗi lệnh. `timeout` bị clamp `1..30s` (`terminal.py:29`).

Defense-in-depth: tool **tự** gọi `classify_terminal` (`terminal.py:21`) *bên cạnh* lớp `SafeToolPort` — kẻ gọi trực tiếp tool (không qua port) vẫn bị chặn.

**Tự kiểm**: `argv=["python","-c","print(1)"]` chạy ok; `argv=["sh","-c","ls"]` → `policy_blocked`. Lệnh treo → `timeout after Ns`.

### Bước 5 — lint_test (`toolbox/lint_test.py`)

3 tool validation: chạy **argv cố định** `sys.executable -m py_compile|ruff|pytest` (`lint_test.py:133,149`) — không bao giờ nhận chuỗi lệnh từ model, nên không mở mặt injection. `ruff` thiếu → degrade `dependency_failure`, không sập.

**Tự kiểm**: `lint_compile path="."` trả `validation=True` + danh sách `failures`; không có cách truyền flag tuỳ ý vào subprocess.

### Bước 6 — code_index (`toolbox/code_index.py`)

4 tool read-only: index symbol (AST cho Python, regex cho JS/TS), find symbol/references, dependency graph. **Read-only tuyệt đối** — không hàm nào ghi. Path qua `resolve_in_workspace` (`code_index.py:159`); loại trừ `.git/.venv/var/...`.

**Tự kiểm**: `code_find_symbol name="Terminal"` trả match có `file:lineno`; chạy 2 lần cho cùng kết quả (idempotent).

### Bước 7 — Middleware chain (`middleware/`)

Năm middleware, mỗi cái là callable `(request, nxt) -> envelope`:
- `TimingLog` (`timing.py:10`) — đo ms, `fail_open=True`.
- `PolicyGate` (`policy.py:9`) — deny-list theo *tên tool*.
- `BudgetGuard` (`budget.py:10`) — chặn gọi lặp y hệt.
- `Retry` (`retry.py:23`) — gọi lại khi `ok=False`.
- `CondenseResult` (`condense.py:11`) — co kết quả, `fail_open=True`, bỏ qua `llm.*`.

Hành trình một request qua chain (ngoài→trong, rồi envelope chảy ngược ra):

```
request → [timing t0] → [policy: tên có trong deny?]
                          → [budget: gọi lặp?] → [retry: bọc core]
                                                   → CORE: SafeToolPort → tool → envelope
                          ← envelope (kèm metadata kind/idempotent)
        ← [timing đo ms, ghi sink]
```

Vì sao thứ tự này: `timing` ngoài cùng để đo *toàn bộ* (kể cả retry). `policy` trước `budget` vì chặn-theo-tên rẻ và dứt khoát hơn đếm-lặp. `retry` *trong cùng* (sát core) để vòng lặp lại chỉ chạy lõi, không kích hoạt lại timing/policy mỗi lần. `condense` sau cùng để co kết quả *đã ổn định*.

### Bước 8 — Wire qua bootstrap (`core/bootstrap.py`)

`toolbox/feature.py::install` (`feature.py:67`): tạo `policy = ToolPolicy()`, lặp `_TOOL_CLASSES`, đăng ký mỗi tool **đã bọc** `SafeToolPort(name, tool, policy)` (`feature.py:74`) kèm descriptor `kind/idempotent/risk` (`feature.py:37`).

`_install_middleware` (`bootstrap.py:28`): `kernel.use(...)` theo thứ tự timing→policy→retry→condense. Vì `kernel.use` đăng ký order = **ngoài→trong** và kernel bọc `reversed` (`core/kernel.py:193`), thứ tự gọi đúng như khai báo. **BudgetGuard cố tình KHÔNG wire ở đây** (`bootstrap.py:30`): counter của nó là per-run, instance sống cùng kernel sẽ rò rỉ giữa các run.

**Tự kiểm cả phase**: `create_kernel()` → `kernel.execute_tool("fs_read", {"path":"x"})` chạy qua middleware + SafeToolPort + jail mà không crash kernel.

## 4. Class & biến kiểm soát (cái neo)

| Neo | File:line | Vai trò kiểm soát |
|---|---|---|
| `resolve_in_workspace()` | `safety/sandbox.py:46` | Path-jail: `resolve()` + `is_relative_to(workspace)` (I8) |
| `_reject_foreign_path_syntax()` | `safety/sandbox.py:25` | Fail-closed lexically với syntax Windows |
| `SafeToolPort` | `safety/policy.py:105` | Một-cửa policy: check trước, mới gọi inner (I9) |
| `ToolPolicy.check` | `safety/policy.py:88` | Nơi DUY NHẤT thêm luật cross-cutting |
| `classify_terminal` | `safety/policy.py:53` | Chặn shell/destructive/git/path-escape |
| `Terminal.execute` | `toolbox/terminal.py:15` | argv-no-shell + timeout clamp |
| envelope metadata `kind/idempotent` | `core/kernel.py:173` | Tín hiệu Retry keys vào |

**Snippet 1 — path-jail (`safety/sandbox.py:46`):**
```python
def resolve_in_workspace(raw_path: str) -> Path:
    workspace = workspace_dir()
    _reject_foreign_path_syntax(raw_path)
    path = Path(raw_path)
    if not path.is_absolute():
        path = workspace / path
    resolved = path.resolve()
    if resolved != workspace and not resolved.is_relative_to(workspace):
        raise SandboxError(f"Path is outside workspace: {raw_path}")
    return resolved
```

**Snippet 2 — một-cửa policy (`safety/policy.py:113`):**
```python
def execute(self, request: ToolRequest) -> dict[str, Any]:
    decision = self._policy.check(request.name, request.args)
    if not decision.allowed:
        return {"ok": False, "tool": request.name, "policy_blocked": True,
                "policy_code": decision.code, "error": decision.reason,
                "metadata": {"risk": decision.risk}}
    return self._inner.execute(request)   # chỉ chạy khi policy cho phép
```

**Snippet 3 — argv-no-shell + timeout (`toolbox/terminal.py:29`):**
```python
timeout = min(max(int(request.args.get("timeout", 10)), 1), 30)
cwd = workspace_dir()
proc = subprocess.run([str(a) for a in argv],   # list, KHÔNG shell=True
                      cwd=str(cwd), capture_output=True,
                      text=True, timeout=timeout)
```

**Snippet 4 — luật chặn shell-injection (`safety/policy.py:56`):**
```python
exe = str(argv[0]).replace("\\", "/").split("/")[-1].lower()
if exe in SHELL_EXES:                       # bash/sh/zsh/cmd/powershell...
    return PolicyDecision(False, ..., "shell_exe", "blocked")
if any(tok in str(part) for part in argv for tok in SHELL_TOKENS):
    return PolicyDecision(False, ..., "shell_token", "blocked")  # | & ; > $( &&
```
Hai dòng này là *lý do* `argv-no-shell` thực sự an toàn: ngay cả khi ai đó truyền `argv=["echo","a; rm b"]`, token `;` bị bắt trước khi tới `subprocess`. Không có shell để diễn giải, và token shell cũng bị từ chối — chặn cả hai đường.

## 5. Invariant của phase

- **I8 — Workspace jail**: mọi tool đụng filesystem PHẢI gọi `resolve_in_workspace(...)` trước khi đọc/ghi; không nhận path tuyệt đối từ model mà không qua jail. Neo: `safety/sandbox.py:46`; áp dụng tại `filesystem.py`, `lint_test.py`, `code_index.py`. (known-risks Part 1 row 6.)
- **I9 — Một-cửa safety**: mỗi tool toolbox bị bọc `SafeToolPort` → policy chokepoint chạy trước inner. Mở rộng luật chỉ ở `ToolPolicy.check` (`safety/policy.py:88`), không rải per-tool. Neo: `toolbox/feature.py:74`.
- **Middleware order (ngoài→trong)**: `timing → policy(deny) → budget → retry → condense`. Khai báo bằng `kernel.use` theo đúng thứ tự đó; kernel bọc `reversed` (`core/kernel.py:193`) nên thứ tự *gọi* = thứ tự *khai báo*. (runtime-flow §5, dòng 98.)

## 6. Pitfall / bug sẽ gặp

**Path traversal vì quên jail**
- *Triệu chứng*: agent đọc/ghi được `/etc/passwd`, file xuất hiện ngoài `var/workspace`.
- *Nguyên nhân*: tool fs mới quên gọi `resolve_in_workspace`. `safety/sandbox.py:46`.
- *Cách tránh*: dòng đầu mọi tool đụng đĩa = `resolve_in_workspace(...)`; bắt `SandboxError` thành `ok=False`. (known-risks Part 1 row 6.)

**Shell-injection vì `shell=True`**
- *Triệu chứng*: `"; rm -rf"` trong arg thực thi như lệnh.
- *Nguyên nhân*: dùng `subprocess.run(cmd, shell=True)` hoặc nhận chuỗi lệnh thay vì argv. Mẫu đúng: `toolbox/terminal.py:33`.
- *Cách tránh*: luôn truyền **list argv**, không `shell=True`; để `classify_terminal` chặn token shell (`safety/policy.py:59`).

**Retry chạy side-effect 2 lần**
- *Triệu chứng*: một `fs_write`/`terminal_run` lỗi rồi bị retry → ghi/chạy hai lần.
- *Nguyên nhân*: `Retry` re-invoke MỌI `ok=False` trừ `policy_block`. `middleware/retry.py:14`. Nó chỉ tha non-idempotent effect nhờ metadata `kind=="effect" và idempotent is False` (`core/kernel.py:173`).
- *Cách tránh*: descriptor mỗi tool effect PHẢI có `idempotent: False` (xem `toolbox/feature.py:40`). Tool có side-effect mà khai `idempotent: True` = bom hẹn giờ. (known-risks Part 2.)
- *Chuỗi an toàn để nhớ*: kernel gắn `kind/idempotent` từ descriptor vào envelope.metadata (`core/kernel.py:173`) → `Retry._retryable` đọc đúng metadata đó (`retry.py:14`) → tha. Mắt xích yếu là *descriptor sai*, không phải retry sai. Khi thêm tool mutating mới, kiểm `_DESCRIPTORS` trước khi kiểm logic retry.

**Deny-list không áp cho tool ngoài toolbox**
- *Triệu chứng*: một capability mới chạy mà chẳng qua policy nào.
- *Nguyên nhân*: chỉ toolbox có `SafeToolPort`+jail; `PolicyGate` ở kernel là **opt-in** (chỉ wire khi config bật, `core/bootstrap.py:38`).
- *Cách tránh*: thêm tool ngoài toolbox → bật `middleware.policy` (deny-list) hoặc bọc safety tương đương. (known-risks Part 2.)

**Nhân đôi same-tool guard**
- *Triệu chứng*: budget chặn sớm/sai, hoặc counter rò giữa các run.
- *Nguyên nhân*: wire `BudgetGuard` ở kernel — counter per-run sống cùng kernel-lifetime. `core/bootstrap.py:30` cố tình bỏ.
- *Cách tránh*: để same-tool guard sống ở graph node (per-run), ĐỪNG double nó ở kernel.

## 7. Definition of Done

Tất cả xanh, offline:

- `tests/test_safety.py` — jail + policy chokepoint chặn traversal/shell.
- `tests/test_toolbox.py` — fs/terminal/index happy path + envelope shape.
- `tests/test_middleware.py` — order chain, retry không retry effect, fail-open.
- `tests/test_file_editor.py` — editor phẫu thuật (count-guard, insert range).
- `tests_audit/test_toolbox_sandbox_rigor.py` — bộ tấn công jail nghiêm ngặt (588 dòng).
- `tests_audit/test_security_boundaries.py` — ranh giới an toàn tổng hợp.

Chạy: `python -m pytest tests/test_safety.py tests/test_toolbox.py tests/test_middleware.py tests/test_file_editor.py tests_audit/test_toolbox_sandbox_rigor.py tests_audit/test_security_boundaries.py -q`

Gate: 100% pass; không tạo file nào ngoài `var/workspace` trong suốt test.

## 8. Vì sao tổ chức thế này giúp kiểm soát

Ba bài học gói trong phase này:

1. **Jail = lớp vật lý, không tin diễn giải**. `resolve_in_workspace` không hỏi "path này có ác ý không" — nó ép *mọi* path về một thư mục rồi kiểm. Kể cả syntax inert trên OS hiện tại cũng bị fail-closed. Kiểm soát đến từ việc **thu hẹp không gian khả thi**, không phải đoán ý đồ.

2. **Một-cửa-safety = một nơi để sửa**. Vì mọi tool đi qua `SafeToolPort` và mọi luật sống trong `ToolPolicy.check`, bạn vá lỗ hổng ở *một* chỗ và cả hệ thống được vá. Defense-in-depth (terminal tự gọi `classify_terminal`) đảm bảo bỏ port vẫn an toàn.

3. **Middleware xếp lớp = mỗi mối lo một lớp mỏng**. Timing không biết gì về retry; retry không biết gì về jail. Mỗi middleware cắt ngang một khía cạnh và *thứ tự* (ngoài→trong) là hợp đồng rõ ràng. Thêm mối lo mới = thêm một lớp, không sửa lõi.

Tổng: **path bị giam, tool bị bọc, mối lo bị tách lớp** — đó là cách trao công cụ nguy hiểm cho agent mà vẫn ngủ ngon.

---
*Điều hướng: ← [Phase 2](phase-2-llm-discipline.md) · → [Phase 4](phase-4-graph-resume.md)*
