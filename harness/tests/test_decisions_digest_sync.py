"""test_decisions_digest_sync.py — the read-fast digest must not drift behind the register.

docs/decisions.md is the append-only source of truth (written via decision_register.py).
docs/decisions-digest.md is a hand-curated read-fast summary with a manual
"append DEC -> update digest" convention and — until this guard — NO enforcement.
It silently fell 17 records behind (header stuck at DEC-72 while the register reached
DEC-89). These pin the digest to the register so a stale summary trips the suite instead
of misleading a reader into re-litigating an already-settled ruling.

Scope: a regression tripwire, not a blocking gate. Whether to auto-generate the digest,
add a pre-ship CI block, or drop the digest entirely is a separate (deferred) design call.
"""
import re
from pathlib import Path

_DOCS = Path(__file__).resolve().parents[2] / "docs"
_REGISTER = _DOCS / "decisions.md"
_DIGEST = _DOCS / "decisions-digest.md"


def _ids(text: str) -> set:
    return {int(n) for n in re.findall(r"DEC-(\d+)", text)}


def _register_status() -> dict:
    """id -> status, parsed from the frontmatter blocks (keys precede the ## header)."""
    status = {}
    cur = None
    for line in _REGISTER.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^id:\s*DEC-(\d+)", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.match(r"^status:\s*(\w+)", line)
        if m and cur is not None:
            status[cur] = m.group(1)
            cur = None
    return status


def test_digest_covers_latest_register_dec():
    register_max = max(_ids(_REGISTER.read_text(encoding="utf-8")))
    digest_max = max(_ids(_DIGEST.read_text(encoding="utf-8")))
    assert digest_max >= register_max, (
        f"decisions-digest.md is stale: it covers up to DEC-{digest_max} but the "
        f"register reached DEC-{register_max}. Refresh docs/decisions-digest.md "
        f"(header coverage + theme clusters + supersede graph)."
    )


def test_digest_mentions_every_superseded_dec():
    superseded = {n for n, st in _register_status().items() if st == "superseded"}
    digest_ids = _ids(_DIGEST.read_text(encoding="utf-8"))
    missing = sorted(superseded - digest_ids)
    assert not missing, (
        f"decisions-digest.md supersede graph is incomplete: register marks "
        f"{['DEC-%d' % n for n in missing]} superseded but the digest never names them."
    )
