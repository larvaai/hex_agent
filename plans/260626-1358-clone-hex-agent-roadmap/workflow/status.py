#!/usr/bin/env python3
"""status.py — render artifact JSON cua harness thanh 1 mat trang thai NGUOI-DOC-DUOC.

Muc dich: ngung doc JSON tho de quan ly. Script quet plans/*/artifacts/{plan-approval,
verification,review-decision}.json, suy verdict + co do, in mot bang gon cho ca du an.

Chay (tu repo root hoac bat ky dau):
    python plans/260626-1358-clone-hex-agent-roadmap/workflow/status.py
    python .../status.py --plans-dir /duong/dan/plans     # override

Offline, chi stdlib. Luon exit 0 (day la bao cao, KHONG phai gate).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

OK, BAD, WARN, SKIP = "✓", "✗", "⚠", "–"  # ✓ ✗ ⚠ –


def _load(p: Path):
    """Doc JSON; tra (data, None) hoac (None, ly_do) neu thieu/hong."""
    if not p.exists():
        return None, "khong co"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, OSError) as e:
        return None, f"khong doc duoc ({type(e).__name__})"


def _approval(d):
    """plan-approval.json -> (dong nguoi-doc, list co_do)."""
    flags = []
    verdict = d.get("verdict", "?")
    author, reviewer = d.get("author", "?"), d.get("reviewer", "?")
    sym = OK if verdict == "APPROVED" else WARN
    if author and author == reviewer:
        flags.append("plan-approval author==reviewer (khong tach vai — soi tay)")
        sym = WARN
    line = f"{sym} {verdict:<9} (author={author} reviewer={reviewer})"
    return line, flags


def _verification(d):
    """verification.json -> (dong, co_do). Bat tu-bao-PASS gian doi."""
    flags = []
    verdict = d.get("verdict", "?")
    checks = d.get("checks", []) or []
    n_pass = sum(1 for c in checks if c.get("status") == "PASS")
    n_fail = sum(1 for c in checks if c.get("status") == "FAIL")
    n_skip = sum(1 for c in checks if c.get("status") == "SKIP")
    empty_detail = sum(1 for c in checks if not (c.get("detail") or "").strip())
    sym = OK if verdict == "PASS" and n_fail == 0 else (WARN if verdict == "PASS_WITH_RISK" else BAD)
    if verdict == "PASS" and n_fail:
        flags.append(f"verdict PASS nhung co {n_fail} check FAIL (tu-bao-PASS gian doi)")
        sym = BAD
    if n_fail:
        flags.append(f"{n_fail} check FAIL -> hard stage (push/pr/ship) bi chan")
    if empty_detail:
        flags.append(f"{empty_detail} check detail rong -> UNVERIFIABLE (chay lai, dan output that)")
    line = f"{sym} {verdict:<14} (checks: {n_pass}{OK} {n_fail}{BAD} {n_skip}{SKIP})"
    return line, flags


def _review(d):
    """review-decision.json -> (dong, co_do)."""
    flags = []
    verdict = d.get("verdict", "?")
    reviewer, role = d.get("reviewer", "?"), d.get("role", "?")
    rationale = (d.get("rationale") or "").strip()
    sym = OK if verdict == "PASS" else (WARN if verdict == "PASS_WITH_RISK" else BAD)
    if verdict == "PASS_WITH_RISK":
        flags.append("review PASS_WITH_RISK != ship license (hard stage van doi dung 'PASS')")
    if verdict == "BLOCKED":
        flags.append("review BLOCKED -> chan pr/ship/deploy")
    if rationale and len(rationale) < 15:
        flags.append("review rationale qua mong ('LGTM') — reviewer da kiem gi?")
    line = f"{sym} {verdict:<14} (reviewer={reviewer} role={role})"
    return line, flags


def _overall(approval, verification, review):
    """1 dong tong: san sang ship / dang chan / chua du."""
    av = approval and approval.get("verdict") == "APPROVED"
    vv = verification and verification.get("verdict")
    rv = review and review.get("verdict")
    if vv == "BLOCKED" or rv == "BLOCKED":
        return f"{BAD} DANG BI CHAN (verify/review BLOCKED) — xem co do"
    if av and vv == "PASS" and rv == "PASS":
        return f"{OK} SAN SANG SHIP (ca 3 giay phep xanh)"
    have = [n for n, ok in (("plan", av), ("verify", vv == "PASS"), ("review", rv == "PASS")) if ok]
    miss = [n for n in ("plan", "verify", "review") if n not in have]
    return f"{WARN} CHUA DU — xanh: {', '.join(have) or 'chua co'} · thieu/chua-PASS: {', '.join(miss)}"


def scan(plans_dir: Path) -> list[tuple[str, list[str], list[str]]]:
    """Tra list (slug, cac_dong, cac_co_do) cho moi plan co thu muc artifacts/."""
    out = []
    for art in sorted(plans_dir.glob("*/artifacts")):
        if not art.is_dir():
            continue
        slug = art.parent.name
        lines, flags = [], []
        raw = {}
        for key, fname, render in (
            ("approval", "plan-approval.json", _approval),
            ("verification", "verification.json", _verification),
            ("review", "review-decision.json", _review),
        ):
            data, err = _load(art / fname)
            raw[key] = data
            label = {"approval": "plan-approval", "verification": "verification ", "review": "review       "}[key]
            if data is None:
                lines.append(f"  {label}: {SKIP} {err}")
                continue
            line, fl = render(data)
            lines.append(f"  {label}: {line}")
            flags.extend(fl)
        lines.append("  -> TONG: " + _overall(raw["approval"], raw["verification"], raw["review"]))
        out.append((slug, lines, flags))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Render harness artifact -> bang trang thai nguoi-doc-duoc.")
    default_plans = Path(__file__).resolve().parents[3] / "plans"
    ap.add_argument("--plans-dir", type=Path, default=default_plans, help=f"mac dinh: {default_plans}")
    args = ap.parse_args()

    print("=" * 72)
    print("HEX_AGENT — BANG TRANG THAI (status.py)  ·  render artifact JSON -> nguoi doc")
    print("=" * 72)

    if not args.plans_dir.exists():
        print(f"(!) khong thay {args.plans_dir} — chay tu repo root hoac dung --plans-dir")
        return 0

    rows = scan(args.plans_dir)
    if not rows:
        print("(chua co plan nao co artifacts/ — chua chay phase nao qua cook/test/review)")
    for slug, lines, flags in rows:
        print(f"\n▌ {slug}")
        for ln in lines:
            print(ln)
        for f in flags:
            print(f"  \U0001f534 {f}")

    print("\n" + "-" * 72)
    print(f"LEGEND: {OK} on · {BAD} FAIL/chan · {WARN} can soi · {SKIP} thieu/skip")
    print("Render 1 file cu the cho de tham:  /hs:explain <path>.json")
    print("Cong hieu (hieu/AC) tu tick o:  plans/260626-1358-clone-hex-agent-roadmap/workflow/STATUS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
