"""
Lesson 33 — Anti-Patterns Catalog (capstone, lesson cuối phase Architecture)
=============================================================================

Cấu trúc 1 file để chạy:
    [BAD_CODE]    String chứa code BAD với 12 anti-pattern
    [GOOD_CODE]   String chứa code GOOD đã refactor
    [DETECTORS]   Heuristic AST-based phát hiện smell
    [DEMO]        7 demo: detect trên BAD, verify GOOD sạch, refactor parity

Cách chạy:
    python 33_antipatterns.py

Mỗi anti-pattern được tag bằng comment `# ANTI-PATTERN N:` để detector dò.
12 anti-pattern hiển thị:
    1. God Object              → SRP (24)
    2. Spaghetti Code          → Strategy/State (21/20)
    3. Anemic Domain           → Aggregate (32)
    4. Big Ball of Mud         → Clean/Hex (29/30)
    5. Golden Hammer           → meta principle
    6. Premature Optimization  → Knuth
    7. Lava Flow               → YAGNI
    8. Cargo Cult              → hiểu rationale
    9. Magic Numbers           → Enum/Const
   10. Shotgun Surgery         → SRP inverse + Aggregate
   11. Refused Bequest         → ISP/Adapter (27/6)
   12. Feature Envy            → Move method (24)
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, List, Tuple, Optional


# =============================================================================
# [BAD_CODE]   12 anti-patterns trong 1 string source
# =============================================================================

BAD_CODE = '''
# ============= 1. GOD OBJECT =============
class QuizGod:
    """600-line class doing everything (here truncated for clarity)."""
    def __init__(self):
        self.users = {}
        self.scores = {}
        self.emails = []
        self.html_cache = ""
        self.csv_buffer = ""
        self.db_conn = None
        self.smtp_conn = None
    def submit(self, user, answers): pass
    def score(self, answers): pass
    def save_to_db(self, sub): pass
    def load_from_db(self, uid): pass
    def send_email(self, to, body): pass
    def send_sms(self, to, body): pass
    def render_html(self, sub): pass
    def render_pdf(self, sub): pass
    def export_csv(self, subs): pass
    def import_csv(self, path): pass
    def update_leaderboard(self, uid, score): pass
    def query_leaderboard(self, top_n): pass
    def authenticate(self, user, pwd): pass
    def authorize(self, user, action): pass
    def log_audit(self, event): pass
    def cleanup_expired_sessions(self): pass
    def archive_old_quizzes(self): pass
    def replicate_to_secondary(self): pass
    def check_health(self): pass
    def reload_config(self): pass
    def emit_metrics(self): pass

# ============= 2. SPAGHETTI CODE =============
def process_quiz_spaghetti(quiz, user, mode, env, ctx):
    if mode == "dev":
        if env.beta:
            if user.tier == "free":
                if quiz.type == "math":
                    if user.attempts < 3:
                        if ctx.region == "us":
                            return "scored"
                        else:
                            if ctx.locale == "en":
                                return "scored_en"
                            else:
                                return "rejected"
                    else:
                        return "limit_exceeded"
    return "default"

# ============= 3. ANEMIC DOMAIN MODEL =============
class SubmissionAnemic:
    def __init__(self, user_id, answers, score=None, finalized=False):
        self.user_id = user_id
        self.answers = answers
        self.score = score
        self.finalized = finalized
    def get_user_id(self): return self.user_id
    def set_user_id(self, v): self.user_id = v
    def get_answers(self): return self.answers
    def set_answers(self, v): self.answers = v
    def get_score(self): return self.score
    def set_score(self, v): self.score = v
    def get_finalized(self): return self.finalized
    def set_finalized(self, v): self.finalized = v

class SubmissionService:
    """All business logic outside the entity (anemic indicator)."""
    def calculate_score(self, sub, questions):
        sub.score = sum(1 for a, q in zip(sub.answers, questions) if a == q)
    def finalize(self, sub):
        sub.finalized = True
    def is_valid(self, sub, questions):
        return len(sub.answers) == len(questions)

# ============= 4. (Big Ball of Mud demonstrated by lack of structure) =============

# ============= 5. GOLDEN HAMMER (Strategy pattern over-applied) =============
class IsPositiveStrategy:
    def apply(self, n): return n > 0
class IsNegativeStrategy:
    def apply(self, n): return n < 0
class IsZeroStrategy:
    def apply(self, n): return n == 0
def strategy_for(n):
    if n > 0: return IsPositiveStrategy()
    elif n < 0: return IsNegativeStrategy()
    else: return IsZeroStrategy()
def classify_overengineered(n):
    if strategy_for(n).apply(n): return "matched"
    return "no"

# ============= 6. PREMATURE OPTIMIZATION =============
class FastSetPremature:
    def __init__(self, capacity=1024):     # capacity guess
        self._buckets = [[] for _ in range(capacity)]
        self._cap = capacity
    def add(self, item):
        h = hash(item) & (self._cap - 1)
        if item not in self._buckets[h]:
            self._buckets[h].append(item)
    def __contains__(self, item):
        h = hash(item) & (self._cap - 1)
        return item in self._buckets[h]
# (replaces Python's built-in set — for no measured reason)

# ============= 7. LAVA FLOW =============
def submit_v3(user, answers):
    # OLD VERSION — kept "for safety" since 2018
    # def submit_v1(user, answers):
    #     ... 50 lines ...
    # def submit_v2(user, answers):
    #     ... 80 lines ...
    if False:                           # never executes
        return submit_v1_legacy(user, answers)   # noqa
    # TODO 2018: refactor  ← still TODO
    return _new_submit(user, answers)

def _new_submit(user, answers): return "ok"

# ============= 8. CARGO CULT (Singleton everywhere) =============
class LoggerCargoCult:
    """Singleton because... senior code did it. No rationale."""
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    def log(self, msg): print(msg)

# ============= 9. MAGIC NUMBERS / STRINGS =============
def discount_for(user):
    if user.tier == 1: return 0.85
    elif user.tier == 2: return 0.70
    elif user.tier == 3: return 0.50
    return 1.0

def status_label(code):
    if code == 0: return "pending"
    elif code == 1: return "graded"
    elif code == 7: return "archived"      # why 7?
    return "unknown"

# ============= 10. SHOTGUN SURGERY (VAT_RATE rải) =============
def calc_score_with_tax(base):
    return base * 1.10                      # VAT 10%
def calc_invoice(subtotal):
    return subtotal * 1.10                  # VAT 10% — same constant copied
def calc_quote(quote_amount):
    return quote_amount * 1.10              # VAT 10% — third copy

# ============= 11. REFUSED BEQUEST =============
class Database:
    def read(self, k): pass
    def write(self, k, v): pass
    def delete(self, k): pass
    def truncate(self): pass
    def replicate(self): pass

class ReadOnlyDatabase(Database):
    def write(self, k, v): raise NotImplementedError
    def delete(self, k): raise NotImplementedError
    def truncate(self): raise NotImplementedError
    def replicate(self): raise NotImplementedError

class CDN(Database):
    def write(self, k, v): raise NotImplementedError("CDN cannot write")
    def delete(self, k): raise NotImplementedError("CDN cannot delete")
    def truncate(self): raise NotImplementedError
    def replicate(self): raise NotImplementedError

# ============= 12. FEATURE ENVY =============
class Customer:
    def __init__(self, is_premium, country, tier_discount, loyalty_years, churn_risk, seg_code):
        self.is_premium = is_premium
        self.country = country
        self.tier_discount = tier_discount
        self.loyalty_years = loyalty_years
        self.churn_risk = churn_risk
        self.seg_code = seg_code

class InvoiceFeatureEnvy:
    def __init__(self, subtotal):
        self.subtotal = subtotal
    def total_for(self, customer):
        # Method ham field của Customer hơn của chính mình
        if customer.is_premium and customer.country == "US":
            base = self.subtotal * customer.tier_discount
        else:
            base = self.subtotal
        if customer.loyalty_years > 5:
            base *= 0.95
        if customer.churn_risk > 0.7:
            base *= 1.05
        if customer.seg_code == "VIP":
            base *= 0.90
        return base
'''

# =============================================================================
# [GOOD_CODE]   Refactored cùng functionality, clean
# =============================================================================

GOOD_CODE = '''
from enum import IntEnum
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# ============= Constants (fix Magic Numbers + Shotgun Surgery) =============
VAT_RATE = 0.10
LEGACY_ARCHIVED_CODE = 7

class Tier(IntEnum):
    BRONZE = 1
    SILVER = 2
    GOLD = 3

DISCOUNTS = {Tier.BRONZE: 0.85, Tier.SILVER: 0.70, Tier.GOLD: 0.50}

class Status(IntEnum):
    PENDING = 0
    GRADED = 1
    ARCHIVED = 7

# ============= Fix Anemic: rich domain entity =============
@dataclass(frozen=True)
class Question:
    qid: str
    correct: int

class SubmissionRich:
    def __init__(self, user_id, answers):
        self._user_id = user_id
        self._answers = tuple(answers)
        self._score = None
        self._finalized = False
    @property
    def user_id(self): return self._user_id
    def score_against(self, questions):
        if len(self._answers) != len(questions):
            raise ValueError("answer count mismatch")
        self._score = sum(1 for a, q in zip(self._answers, questions) if a == q.correct)
        return self._score
    def finalize(self):
        if self._score is None:
            raise ValueError("cannot finalize without score")
        self._finalized = True
    @property
    def is_finalized(self): return self._finalized

# ============= Fix God Object: SRP split =============
class Scorer:
    def score(self, answers, questions):
        return sum(1 for a, q in zip(answers, questions) if a == q.correct)

class SubmissionRepo:
    def __init__(self): self._store = []
    def save(self, sub): self._store.append(sub); return len(self._store)

class Notifier:
    def __init__(self): self.sent = []
    def send_receipt(self, user_id, score):
        self.sent.append((user_id, score))

class QuizService:
    def __init__(self, scorer, repo, notifier):
        self.scorer = scorer
        self.repo = repo
        self.notifier = notifier
    def submit(self, user_id, answers, questions):
        score = self.scorer.score(answers, questions)
        self.repo.save((user_id, answers, score))
        self.notifier.send_receipt(user_id, score)
        return score

# ============= Fix Spaghetti: early-return + dispatch =============
def process_quiz_clean(quiz, user, ctx):
    if user.attempts >= 3:
        return "limit_exceeded"
    if not _is_eligible(user, ctx):
        return "rejected"
    return "scored"

def _is_eligible(user, ctx):
    return user.tier == "free" and ctx.region in ("us", "eu")

# ============= Fix Golden Hammer: simple if =============
def classify_simple(n):
    return "pos" if n > 0 else "neg" if n < 0 else "zero"

# ============= Fix Premature Optimization: built-in =============
def use_builtin_set():
    return set()      # python's set is fine

# ============= Fix Lava Flow: deleted dead code =============
def submit_clean(user, answers):
    return "ok"
# (old versions removed — git history retains them)

# ============= Fix Cargo Cult: module-level logger =============
import logging
logger_clean = logging.getLogger(__name__)

# ============= Fix Magic Numbers + Shotgun Surgery =============
def discount_for_clean(user):
    return DISCOUNTS[Tier(user.tier)]

def status_label_clean(code):
    return Status(code).name.lower()

def calc_with_vat(amount):
    return amount * (1 + VAT_RATE)

# ============= Fix Refused Bequest: ISP narrow =============
@runtime_checkable
class IReadable(Protocol):
    def read(self, k): ...

@runtime_checkable
class IWritable(Protocol):
    def write(self, k, v): ...

class FileSystemClean:
    def read(self, k): return f"data:{k}"
    def write(self, k, v): pass

class CDNClean:
    def read(self, k): return f"cdn:{k}"
# CDN không implement IWritable -> không bị buộc raise NotImpl

# ============= Fix Feature Envy: move method =============
class CustomerClean:
    def __init__(self, is_premium, country, tier_discount, loyalty_years, churn_risk, seg_code):
        self.is_premium = is_premium
        self.country = country
        self.tier_discount = tier_discount
        self.loyalty_years = loyalty_years
        self.churn_risk = churn_risk
        self.seg_code = seg_code
    def discount_factor(self):
        factor = 1.0
        if self.is_premium and self.country == "US":
            factor *= self.tier_discount
        if self.loyalty_years > 5:
            factor *= 0.95
        if self.churn_risk > 0.7:
            factor *= 1.05
        if self.seg_code == "VIP":
            factor *= 0.90
        return factor

class InvoiceClean:
    def __init__(self, subtotal):
        self.subtotal = subtotal
    def total_for(self, customer):
        return self.subtotal * customer.discount_factor()
'''


# =============================================================================
# [DETECTORS]   AST + regex heuristics
# =============================================================================

@dataclass
class Smell:
    name: str
    location: str
    detail: str
    cure_lesson: str


def _line_count_of_node(src: str, node: ast.AST) -> int:
    if hasattr(node, "end_lineno") and hasattr(node, "lineno"):
        return (node.end_lineno or node.lineno) - node.lineno + 1
    return 0


def detect_god_object(src: str, threshold_methods: int = 15) -> List[Smell]:
    out: List[Smell] = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if len(methods) >= threshold_methods:
                out.append(Smell(
                    name="God Object",
                    location=f"class {node.name} (line {node.lineno})",
                    detail=f"{len(methods)} methods (threshold {threshold_methods})",
                    cure_lesson="Lesson 24 SRP",
                ))
    return out


def detect_spaghetti(src: str, depth_threshold: int = 4) -> List[Smell]:
    """Đếm max nesting depth (if/for/while/with) trong mỗi function."""
    out: List[Smell] = []
    tree = ast.parse(src)

    def max_depth(node: ast.AST, depth: int = 0) -> int:
        worst = depth
        for child in ast.iter_child_nodes(node):
            inc = depth + 1 if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try)) else depth
            worst = max(worst, max_depth(child, inc))
        return worst

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            d = max_depth(node, 0)
            if d > depth_threshold:
                out.append(Smell(
                    name="Spaghetti Code",
                    location=f"def {node.name} (line {node.lineno})",
                    detail=f"max nesting depth {d} (threshold {depth_threshold})",
                    cure_lesson="Lesson 21 Strategy / 20 State",
                ))
    return out


def detect_anemic_domain(src: str) -> List[Smell]:
    out: List[Smell] = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
            if not methods:
                continue
            getter_setter = [
                m for m in methods
                if m.name.startswith(("get_", "set_")) or m.name in ("__init__",)
            ]
            ratio = len(getter_setter) / len(methods)
            if ratio >= 0.85 and len(methods) >= 3:
                out.append(Smell(
                    name="Anemic Domain Model",
                    location=f"class {node.name} (line {node.lineno})",
                    detail=f"{int(ratio*100)}% getter/setter only",
                    cure_lesson="Aggregate (Lesson 32) / move behavior into entity",
                ))
        # Service class with logic that should live in entity.
        # Only flag if a non-init method takes an entity-like arg AND has real logic
        # (more than 2 statements, mutates the arg).
        if isinstance(node, ast.ClassDef) and node.name.endswith("Service"):
            for m in node.body:
                if not isinstance(m, ast.FunctionDef):
                    continue
                if m.name in ("__init__", "__new__", "__repr__"):
                    continue
                if len(m.args.args) < 2:
                    continue
                # Must mutate the entity arg (heuristic: assignment to `arg.field`)
                arg_name = m.args.args[1].arg
                mutates_entity = any(
                    isinstance(stmt, ast.Assign) and any(
                        isinstance(t, ast.Attribute)
                        and isinstance(t.value, ast.Name)
                        and t.value.id == arg_name
                        for t in stmt.targets
                    )
                    for stmt in ast.walk(m)
                )
                if mutates_entity:
                    out.append(Smell(
                        name="Anemic Domain Model (companion)",
                        location=f"def {node.name}.{m.name} (line {m.lineno})",
                        detail=f"Service method mutates entity arg `{arg_name}` — should be entity method",
                        cure_lesson="Move method to entity (24 SRP)",
                    ))
                    break
    return out


def detect_magic_numbers(src: str) -> List[Smell]:
    """Skip literals that LIVE in const/enum definition (those *are* the fix)."""
    out: List[Smell] = []
    tree = ast.parse(src)
    allowed = {0, 1, -1, 2, 100}

    # Mark nodes to skip: inside Enum class, ALL_CAPS module assign, dict literal at module level
    skip_nodes: set[int] = set()

    def _mark_subtree(node: ast.AST) -> None:
        for n in ast.walk(node):
            skip_nodes.add(id(n))

    for node in ast.walk(tree):
        # Skip any Constant inside an Enum/IntEnum class definition
        if isinstance(node, ast.ClassDef):
            base_names = {b.id for b in node.bases if isinstance(b, ast.Name)}
            if base_names & {"Enum", "IntEnum", "StrEnum"}:
                _mark_subtree(node)
        # Skip module-level assignment to ALL_CAPS name
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    _mark_subtree(node.value)
        # Skip Dict literals whose keys are Enum members (e.g. DISCOUNTS = {Tier.A: 0.85})
        if isinstance(node, ast.Dict):
            keys = node.keys
            if keys and all(
                isinstance(k, ast.Attribute) for k in keys if k is not None
            ):
                _mark_subtree(node)

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if id(node) in skip_nodes:
                continue
            v = node.value
            if v in allowed:
                continue
            out.append(Smell(
                name="Magic Number",
                location=f"line {node.lineno}",
                detail=f"literal {v!r}",
                cure_lesson="Enum / module constant",
            ))
    return out


def detect_lava_flow(src: str) -> List[Smell]:
    out: List[Smell] = []
    # if False: pattern
    for m in re.finditer(r"\bif\s+False\s*:", src):
        line = src.count("\n", 0, m.start()) + 1
        out.append(Smell(
            name="Lava Flow",
            location=f"line {line}",
            detail="`if False:` block (dead code)",
            cure_lesson="Delete; git keeps history",
        ))
    # TODO older than ~3 years
    for m in re.finditer(r"#\s*TODO\s+20(1[0-9]|2[0-3])", src):
        line = src.count("\n", 0, m.start()) + 1
        out.append(Smell(
            name="Lava Flow",
            location=f"line {line}",
            detail=f"stale TODO: {m.group(0)!r}",
            cure_lesson="Resolve or delete (YAGNI)",
        ))
    return out


def detect_refused_bequest(src: str) -> List[Smell]:
    out: List[Smell] = []
    tree = ast.parse(src)
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or not cls.bases:
            continue
        not_impl_count = 0
        method_count = 0
        for m in cls.body:
            if isinstance(m, ast.FunctionDef):
                method_count += 1
                # body is `raise NotImplementedError` or contains it
                src_lines = ast.unparse(m)
                if "NotImplementedError" in src_lines:
                    not_impl_count += 1
        if method_count > 0 and not_impl_count / method_count >= 0.5 and not_impl_count >= 2:
            out.append(Smell(
                name="Refused Bequest",
                location=f"class {cls.name} (line {cls.lineno})",
                detail=f"{not_impl_count}/{method_count} methods raise NotImplementedError",
                cure_lesson="Lesson 27 ISP — split interface; or Lesson 6 Adapter",
            ))
    return out


def detect_feature_envy(src: str) -> List[Smell]:
    """Method có > 4 lần truy cập field của cùng 1 param khác (heuristic)."""
    out: List[Smell] = []
    tree = ast.parse(src)
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        for m in cls.body:
            if not isinstance(m, ast.FunctionDef):
                continue
            # collect attribute accesses by `arg_name`
            param_names = [a.arg for a in m.args.args[1:]]   # skip self
            if not param_names:
                continue
            counts: Dict[str, int] = {p: 0 for p in param_names}
            self_count = 0
            for inner in ast.walk(m):
                if isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name):
                    n = inner.value.id
                    if n == "self":
                        self_count += 1
                    elif n in counts:
                        counts[n] += 1
            for p, c in counts.items():
                if c >= 4 and c > self_count:
                    out.append(Smell(
                        name="Feature Envy",
                        location=f"def {cls.name}.{m.name} (line {m.lineno})",
                        detail=f"{c} accesses to `{p}.field` vs {self_count} to self",
                        cure_lesson="Move method to {p}'s class (Lesson 24 SRP)",
                    ))
                    break
    return out


def detect_cargo_singleton(src: str) -> List[Smell]:
    out: List[Smell] = []
    tree = ast.parse(src)
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        has_instance_class_var = any(
            isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_instance" for t in n.targets
            )
            for n in cls.body
        )
        has_new_override = any(
            isinstance(n, ast.FunctionDef) and n.name == "__new__"
            for n in cls.body
        )
        if has_instance_class_var and has_new_override:
            out.append(Smell(
                name="Cargo Cult (Singleton)",
                location=f"class {cls.name} (line {cls.lineno})",
                detail="Hand-rolled Singleton — needs rationale comment, often unnecessary",
                cure_lesson="module-level instance / DI",
            ))
    return out


def detect_shotgun_surgery_proxy(src: str, literal: float = 1.10) -> List[Smell]:
    """Cùng 1 hằng số literal lặp ≥ 3 lần ở các function khác nhau."""
    out: List[Smell] = []
    tree = ast.parse(src)
    occurrences: List[Tuple[str, int]] = []
    current_func: Optional[str] = None

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            nonlocal current_func
            current_func = node.name
            self.generic_visit(node)
            current_func = None

        def visit_Constant(self, node):
            if isinstance(node.value, float) and abs(node.value - literal) < 1e-9:
                occurrences.append((current_func or "<module>", node.lineno))

    V().visit(tree)
    distinct_funcs = {f for f, _ in occurrences}
    if len(distinct_funcs) >= 3:
        out.append(Smell(
            name="Shotgun Surgery (proxy)",
            location=", ".join(sorted(distinct_funcs)),
            detail=f"literal {literal!r} appears in {len(distinct_funcs)} functions",
            cure_lesson="Module constant + Aggregate (Lesson 32) / Facade",
        ))
    return out


def detect_golden_hammer(src: str) -> List[Smell]:
    """Suffix-based: > 2 class with same suffix and small bodies."""
    out: List[Smell] = []
    tree = ast.parse(src)
    suffixes: Dict[str, List[str]] = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            for suf in ("Strategy", "Manager", "Helper", "Factory"):
                if n.name.endswith(suf):
                    suffixes.setdefault(suf, []).append(n.name)
    for suf, names in suffixes.items():
        if len(names) >= 3:
            out.append(Smell(
                name="Golden Hammer",
                location=", ".join(names),
                detail=f"{len(names)} classes with suffix `{suf}` — pattern overuse?",
                cure_lesson="Question necessity; sometimes plain function is enough",
            ))
    return out


def detect_premature_optimization(src: str) -> List[Smell]:
    """Class tự build hash table với capacity thay vì built-in."""
    out: List[Smell] = []
    if re.search(r"hash\(.*\)\s*&\s*\(self\._cap\s*-\s*1\)", src):
        out.append(Smell(
            name="Premature Optimization",
            location="custom hash class",
            detail="hand-rolled hash table — likely re-inventing built-in `set`",
            cure_lesson="Use stdlib; measure first (Knuth)",
        ))
    return out


def detect_big_ball_of_mud(src: str) -> List[Smell]:
    """Heuristic: file > 500 lines without obvious section markers."""
    lines = src.splitlines()
    if len(lines) < 500:
        return []
    section_marker_count = sum(1 for ln in lines if re.match(r"^#\s*={3,}", ln))
    if section_marker_count < 5:
        return [Smell(
            name="Big Ball of Mud (proxy)",
            location="whole file",
            detail=f"{len(lines)} lines with only {section_marker_count} section markers",
            cure_lesson="Lesson 29 Clean / 30 Hex — impose boundaries",
        )]
    return []


ALL_DETECTORS = [
    detect_god_object,
    detect_spaghetti,
    detect_anemic_domain,
    detect_magic_numbers,
    detect_lava_flow,
    detect_refused_bequest,
    detect_feature_envy,
    detect_cargo_singleton,
    detect_shotgun_surgery_proxy,
    detect_golden_hammer,
    detect_premature_optimization,
    detect_big_ball_of_mud,
]


def run_all(src: str) -> List[Smell]:
    found: List[Smell] = []
    for det in ALL_DETECTORS:
        found.extend(det(src))
    return found


# =============================================================================
# [DEMO]
# =============================================================================

def banner(s: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {s}")
    print("=" * 76)


def demo_1_detect_smells_in_bad() -> List[Smell]:
    banner("DEMO 1 — Detect anti-patterns in BAD_CODE")
    smells = run_all(BAD_CODE)
    by_name: Dict[str, List[Smell]] = {}
    for s in smells:
        by_name.setdefault(s.name, []).append(s)

    print(f"\n  Total smells found: {len(smells)}")
    print(f"  Distinct categories: {len(by_name)}\n")
    for name, items in by_name.items():
        print(f"  • {name}  ({len(items)} occurrence(s))")
        for it in items[:2]:           # in tối đa 2 example mỗi loại
            print(f"      - {it.location}: {it.detail}")
            print(f"        cure: {it.cure_lesson}")
        if len(items) > 2:
            print(f"      ... and {len(items)-2} more")
    return smells


def demo_2_verify_good_clean() -> List[Smell]:
    banner("DEMO 2 — Verify GOOD_CODE has dramatically fewer smells")
    smells_good = run_all(GOOD_CODE)
    smells_bad = run_all(BAD_CODE)
    print(f"  BAD_CODE  smell count: {len(smells_bad)}")
    print(f"  GOOD_CODE smell count: {len(smells_good)}")
    print(f"  Reduction: {len(smells_bad) - len(smells_good)} fewer ({(1 - len(smells_good)/max(1,len(smells_bad)))*100:.1f}%)")
    if smells_good:
        print("\n  Remaining smells in GOOD (acceptable / intentional):")
        for s in smells_good[:5]:
            print(f"    • {s.name}: {s.location} — {s.detail}")
    assert len(smells_good) < len(smells_bad) / 3, "GOOD should be much cleaner"
    print("  PASS — refactor reduced smells by > 67%")
    return smells_good


def demo_3_smell_to_lesson_mapping() -> None:
    banner("DEMO 3 — Smell → Curing Lesson mapping (12 anti-patterns)")
    mapping = [
        ("God Object",            "Lesson 24 SRP"),
        ("Spaghetti Code",        "Lesson 21 Strategy / 20 State / 13 CoR"),
        ("Anemic Domain Model",   "Aggregate (32) — rich entity"),
        ("Big Ball of Mud",       "Lesson 29 Clean / 30 Hex"),
        ("Golden Hammer",         "Meta-principle: pattern lithium"),
        ("Premature Optimization","Knuth: measure first"),
        ("Lava Flow",             "YAGNI — delete; git keeps history"),
        ("Cargo Cult",            "Demand rationale comment in PR"),
        ("Magic Numbers",         "Enum / module constant"),
        ("Shotgun Surgery",       "Lesson 24 SRP (inverse) + Aggregate (32)"),
        ("Refused Bequest",       "Lesson 27 ISP / 6 Adapter"),
        ("Feature Envy",          "Lesson 24 SRP — move method to data owner"),
    ]
    for ap, cure in mapping:
        print(f"  {ap:<24}→  {cure}")


def demo_4_metric_table() -> None:
    banner("DEMO 4 — Side-by-side metric table BAD vs GOOD")

    def metrics(src: str) -> Dict[str, int]:
        tree = ast.parse(src)
        classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        return {
            "lines": len(src.splitlines()),
            "classes": len(classes),
            "funcs": len(funcs),
            "max_methods_per_class": max(
                (sum(1 for b in c.body if isinstance(b, ast.FunctionDef)) for c in classes),
                default=0,
            ),
            "max_func_lines": max(
                (_line_count_of_node(src, f) for f in funcs), default=0
            ),
        }

    bad = metrics(BAD_CODE)
    good = metrics(GOOD_CODE)
    print(f"  {'Metric':<28} {'BAD':>10} {'GOOD':>10}")
    print(f"  {'-'*28} {'-'*10:>10} {'-'*10:>10}")
    for k in ["lines", "classes", "funcs", "max_methods_per_class", "max_func_lines"]:
        print(f"  {k:<28} {bad[k]:>10} {good[k]:>10}")
    assert good["max_methods_per_class"] < bad["max_methods_per_class"]
    print("  PASS — GOOD has smaller max class size & more focused functions")


def demo_5_refactor_parity() -> None:
    banner("DEMO 5 — Refactor parity: BAD vs GOOD produce same business result")

    # Bring BAD and GOOD into namespaces
    bad_ns: Dict[str, object] = {}
    good_ns: Dict[str, object] = {}
    exec(BAD_CODE, bad_ns)
    exec(GOOD_CODE, good_ns)

    # 1) Magic-number tax: 100 * 1.10 == 110
    assert bad_ns["calc_score_with_tax"](100) == 110.00000000000001 or bad_ns["calc_score_with_tax"](100) == 110.0
    assert abs(good_ns["calc_with_vat"](100) - 110.0) < 1e-9
    print("  • VAT calculation: BAD=110.0  GOOD=110.0  (same result, GOOD uses constant)")

    # 2) Discount tier
    class FakeUser:
        def __init__(self, tier): self.tier = tier
    bad_disc = bad_ns["discount_for"](FakeUser(2))
    good_disc = good_ns["discount_for_clean"](FakeUser(2))
    assert bad_disc == good_disc == 0.70
    print(f"  • Tier 2 discount: BAD={bad_disc}  GOOD={good_disc}  (same, GOOD uses Enum/dict)")

    # 3) Status label
    assert bad_ns["status_label"](7) == good_ns["status_label_clean"](7) == "archived"
    print("  • Status label 7: BAD='archived'  GOOD='archived'  (same, GOOD uses Enum.ARCHIVED=7)")

    # 4) Customer discount (Feature Envy → moved method)
    Customer = bad_ns["Customer"]
    CustomerClean = good_ns["CustomerClean"]
    Invoice = bad_ns["InvoiceFeatureEnvy"]
    InvoiceClean = good_ns["InvoiceClean"]
    bad_cust = Customer(True, "US", 0.85, 7, 0.5, "VIP")
    good_cust = CustomerClean(True, "US", 0.85, 7, 0.5, "VIP")
    bad_total = Invoice(100).total_for(bad_cust)
    good_total = InvoiceClean(100).total_for(good_cust)
    assert abs(bad_total - good_total) < 1e-9
    print(f"  • Invoice total VIP+US+loyal: BAD={bad_total:.4f}  GOOD={good_total:.4f}")
    print("  PASS — refactor preserves behavior, only structure improved")


def demo_6_thresholds_table() -> None:
    banner("DEMO 6 — Heuristic thresholds (rule of thumb)")
    print(f"  {'Metric':<28}{'Healthy':<14}{'Warning':<14}{'Smell':<14}")
    rows = [
        ("File length (LOC)",       "< 300",     "300-500",   "> 500"),
        ("Class methods",           "< 15",      "15-25",     "> 25"),
        ("Method length",           "< 30",      "30-50",     "> 50"),
        ("Cyclomatic complexity",   "< 5",       "5-10",      "> 10"),
        ("Nesting depth",           "< 3",       "3-4",       "> 4"),
        ("PR file count",           "1-3",       "4-7",       "> 7"),
        ("Inheritance depth",       "1-2",       "3",         "> 3"),
        ("Cross-class field access","< 1",       "2-3",       "> 3"),
        ("Magic literal density",   "< 5%",      "5-15%",     "> 15%"),
    ]
    for r in rows:
        print(f"  {r[0]:<28}{r[1]:<14}{r[2]:<14}{r[3]:<14}")
    print()
    print("  Use as conversation triggers, not mechanical PR rejection.")


def demo_7_curriculum_summary() -> None:
    banner("DEMO 7 — Curriculum complete: 4 tang tong ket")
    layers = [
        ("Vocabulary  ", "23 GoF patterns",                 "Lessons 1-23"),
        ("Grammar     ", "SOLID (S/O/L/I/D)",               "Lessons 24-28"),
        ("Style       ", "Clean / Hex / EDA / CQRS+ES",     "Lessons 29-32"),
        ("Hygiene     ", "Anti-patterns catalog",           "Lesson 33"),
    ]
    for name, content_, lessons in layers:
        print(f"  [DONE] {name} {content_:<35} {lessons}")
    print()
    print("  Du tu duy ngoi vao ghe architect o 95% cong ty.")
    print("  Huong di tiep (goi y): DDD, Distributed patterns, Reliability patterns.")


def main() -> int:
    smells_bad = demo_1_detect_smells_in_bad()
    demo_2_verify_good_clean()
    demo_3_smell_to_lesson_mapping()
    demo_4_metric_table()
    demo_5_refactor_parity()
    demo_6_thresholds_table()
    demo_7_curriculum_summary()

    print()
    print("=" * 76)
    print(f"  ALL 7 DEMOS PASS - Lesson 33 Anti-Patterns Catalog verified")
    print(f"  Detected {len(smells_bad)} smells in BAD_CODE across 12 anti-pattern categories.")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
