---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Phase 5 — Verification gate

**Goal**: chứng minh reorg không phá gì (AC #1–#7). Không advance nếu một bước đỏ.

## Step 1 — regenerate MAP (giữ root)
```bash
python tools/gen_map.py
git diff --stat MAP.md   # MAP regenerate sạch, vẫn ở root
```

## Step 2 — smoke + test (chứng minh sửa docstring an toàn — R2)
```bash
python run_smoke.py                 # kỳ vọng: CORE_AGENT_SMOKE_OK
python -m pytest                    # xanh
python -m pytest tests_audit        # xanh (strict audit)
```

## Step 3 — link audit (R1) — 0 link .md gãy
```bash
# liệt kê mọi link nội bộ rồi kiểm tồn tại
grep -rnoE "\]\(([^)]+\.md)\)" docs/ README.md | ...   # với mỗi target: test -f
grep -rnE "rebuild_from_zero|HOW_TO_FOLLOW|NEW_REPO_BUILD_GUIDE|architecture/MCP_TOOLS|ChatGPTCodex" docs/ README.md CHANGELOG.md
```
Kỳ vọng: lệnh 2 trả 0 dòng (không còn trỏ path cũ). Mọi `](*.md)` resolve tới file tồn tại.

## Step 4 — md-location invariant
```bash
find . -name '*.md' -not -path './docs/*' -not -path './plans/*' -not -path './harness/*' \
       -not -path './.git/*' -not -name README.md -not -name CHANGELOG.md -not -name CLAUDE.md
```
Kỳ vọng: rỗng (mọi md ngoài docs/plans đều là whitelist root: README, CHANGELOG, CLAUDE).

## Step 5 — cây đích khớp Expected output
```bash
find docs -maxdepth 2 -type d | sort     # so với plan.md Expected output
git status --short                        # xác nhận R = rename (history preserved)
```

## Acceptance (= AC plan)
- [ ] gen_map sạch, MAP.md ở root (#1)
- [ ] CORE_AGENT_SMOKE_OK (#2)
- [ ] pytest + tests_audit xanh (#3)
- [ ] 0 link .md gãy (#4)
- [ ] md-location invariant giữ (#5)
- [ ] cây docs/ khớp + git rename (#6)
- [ ] 5 docstring trỏ path mới (#7)

## Nếu đỏ
- pytest đỏ → khả năng docstring sửa sai path/cú pháp → soi phase 2 step 5.
- link gãy → soi grep phase 1 step 5 + phase 2 step 6.
- Rollback toàn cục: xem plan.md §Rollback.
