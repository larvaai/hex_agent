# Strict audit suite

Xem `AUDIT_MATRIX.md` Ä‘á»ƒ biáº¿t module nÃ o Ä‘Æ°á»£c suite nÃ o sá»Ÿ há»¯u, vÃ 
`AUDIT_REPORT.md` Ä‘á»ƒ xem failure ledger hiá»‡n táº¡i.

Suite này độc lập với `tests/` và nhắm vào failure modes mà happy-path/acceptance tests dễ bỏ sót:

- property-based + deterministic fuzz;
- contract/envelope/schema round-trip;
- malformed tool/middleware/observer behavior;
- security/path/input adversarial cases;
- concurrency/isolation/idempotency;
- crash/checkpoint/resume matrices;
- UI HTTP black-box + frontend DOM/source contract;
- configuration/plugin/CLI/tooling behavior;
- explicit regression tests cho finding nghiêm trọng.

Không dùng `xfail` và không hạ assertion để làm suite xanh. Optional infrastructure duy nhất là
Qdrant integration cũ ở `tests/`; audit tests dùng fake adapters và chạy offline.

## Install

```powershell
python -m pip install -e ".[dev,audit]"
```

## Run

```powershell
# Chỉ strict audit suite
python -m pytest tests_audit -q

# Acceptance + audit
python -m pytest tests tests_audit -q

# Branch coverage report
python -m pytest tests tests_audit `
  --cov=core --cov=adapters --cov=delegation --cov=discipline --cov=features `
  --cov=graph --cov=llm --cov=middleware --cov=observability --cov=orchestrator `
  --cov=rag --cov=roles --cov=safety --cov=skills --cov=supervisor --cov=toolbox --cov=ui `
  --cov-branch --cov-report=term-missing
```

## Policy

- Audit failure là bằng chứng cần triage, không phải lý do thêm `xfail`.
- Bug security/correctness được giữ bằng regression test cho đến khi production fix.
- Test phải có oracle độc lập hoặc invariant rõ; không assert lại implementation.
- Random/property tests dùng Hypothesis deterministic profile để có thể tái hiện.
- Mọi test có I/O dùng temp directory; không ghi vào workspace/run thật.
