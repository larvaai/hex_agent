"""
Lesson 15 — Interpreter Pattern
Neuroscience analogy: Wernicke's area — phoneme stream → AST → meaning

Cấu trúc file:
  1. AST classes (immutable Expression hierarchy)
  2. Context (variable env + lexicon + semantic memory)
  3. Lexer (analog: STG — phoneme/word boundary)
  4. Parser (analog: Wernicke — recursive descent với precedence)
  5. Visitors (PrettyPrint, Optimize, ToSQL) — operations trên AST
  6. Ví dụ 1 — Boolean expression eval
  7. Ví dụ 2 — Hỏng/thiếu (parse error, name error, type error)
  8. Ví dụ 3 — Ellumm Lesson Query DSL
  9. Test runner — chạy `python 15_interpreter.py`
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, List, Optional, Union


# ============================================================================
# 1. AST CLASSES — immutable Expression hierarchy
# ============================================================================
class Expr(ABC):
    """AbstractExpression. Tất cả node AST kế thừa."""

    @abstractmethod
    def interpret(self, ctx: "Context") -> Any: ...

    @abstractmethod
    def accept(self, visitor: "Visitor") -> Any: ...


# ---- Terminal expressions (leaves) ----
@dataclass(frozen=True)
class NumLit(Expr):
    value: float

    def interpret(self, ctx: "Context") -> float:
        return self.value

    def accept(self, visitor: "Visitor") -> Any:
        return visitor.visit_num(self)


@dataclass(frozen=True)
class StrLit(Expr):
    value: str

    def interpret(self, ctx: "Context") -> str:
        return self.value

    def accept(self, visitor: "Visitor") -> Any:
        return visitor.visit_str(self)


@dataclass(frozen=True)
class BoolLit(Expr):
    value: bool

    def interpret(self, ctx: "Context") -> bool:
        return self.value

    def accept(self, visitor: "Visitor") -> Any:
        return visitor.visit_bool(self)


@dataclass(frozen=True)
class VarRef(Expr):
    name: str

    def interpret(self, ctx: "Context") -> Any:
        return ctx.lookup(self.name)

    def accept(self, visitor: "Visitor") -> Any:
        return visitor.visit_var(self)


# ---- Non-terminal expressions (composite) ----
@dataclass(frozen=True)
class And(Expr):
    left: Expr
    right: Expr

    def interpret(self, ctx: "Context") -> bool:
        l = self.left.interpret(ctx)
        if not isinstance(l, bool):
            raise TypeError(f"AND yêu cầu bool, gặp {type(l).__name__}")
        if not l:
            return False  # short-circuit
        r = self.right.interpret(ctx)
        if not isinstance(r, bool):
            raise TypeError(f"AND yêu cầu bool, gặp {type(r).__name__}")
        return r

    def accept(self, visitor: "Visitor") -> Any:
        return visitor.visit_and(self)


@dataclass(frozen=True)
class Or(Expr):
    left: Expr
    right: Expr

    def interpret(self, ctx: "Context") -> bool:
        l = self.left.interpret(ctx)
        if not isinstance(l, bool):
            raise TypeError(f"OR yêu cầu bool, gặp {type(l).__name__}")
        if l:
            return True  # short-circuit
        r = self.right.interpret(ctx)
        if not isinstance(r, bool):
            raise TypeError(f"OR yêu cầu bool, gặp {type(r).__name__}")
        return r

    def accept(self, visitor: "Visitor") -> Any:
        return visitor.visit_or(self)


@dataclass(frozen=True)
class Not(Expr):
    inner: Expr

    def interpret(self, ctx: "Context") -> bool:
        v = self.inner.interpret(ctx)
        if not isinstance(v, bool):
            raise TypeError(f"NOT yêu cầu bool, gặp {type(v).__name__}")
        return not v

    def accept(self, visitor: "Visitor") -> Any:
        return visitor.visit_not(self)


@dataclass(frozen=True)
class Less(Expr):
    left: Expr
    right: Expr

    def interpret(self, ctx: "Context") -> bool:
        l, r = self.left.interpret(ctx), self.right.interpret(ctx)
        if not (isinstance(l, (int, float)) and isinstance(r, (int, float))):
            raise TypeError(f"< yêu cầu số, gặp {type(l).__name__} và {type(r).__name__}")
        return l < r

    def accept(self, visitor: "Visitor") -> Any:
        return visitor.visit_less(self)


@dataclass(frozen=True)
class Equal(Expr):
    left: Expr
    right: Expr

    def interpret(self, ctx: "Context") -> bool:
        return self.left.interpret(ctx) == self.right.interpret(ctx)

    def accept(self, visitor: "Visitor") -> Any:
        return visitor.visit_equal(self)


# ============================================================================
# 2. CONTEXT — variable env + lexicon
# ============================================================================
class Context:
    def __init__(self, vars: Optional[dict] = None):
        self._vars = vars or {}

    def lookup(self, name: str) -> Any:
        if name not in self._vars:
            raise NameError(f"Tên '{name}' không định nghĩa trong context")
        return self._vars[name]

    def with_(self, **kwargs) -> "Context":
        """Trả Context mới với extra biến — immutable update."""
        new_vars = dict(self._vars)
        new_vars.update(kwargs)
        return Context(new_vars)


# ============================================================================
# 3. LEXER — STG: phoneme/word boundary
# ============================================================================
class TokenType(Enum):
    NUMBER = "NUMBER"
    STRING = "STRING"
    IDENT = "IDENT"
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    LESS = "<"
    EQUAL = "="
    LPAREN = "("
    RPAREN = ")"
    EOF = "EOF"


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: Any
    pos: int  # vị trí trong source — quan trọng cho error message


class LexError(SyntaxError):
    pass


KEYWORDS = {"AND": TokenType.AND, "OR": TokenType.OR, "NOT": TokenType.NOT}


def tokenize(source: str) -> List[Token]:
    tokens: List[Token] = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c.isspace():
            i += 1
            continue
        if c == "(":
            tokens.append(Token(TokenType.LPAREN, "(", i))
            i += 1
        elif c == ")":
            tokens.append(Token(TokenType.RPAREN, ")", i))
            i += 1
        elif c == "<":
            tokens.append(Token(TokenType.LESS, "<", i))
            i += 1
        elif c == "=":
            tokens.append(Token(TokenType.EQUAL, "=", i))
            i += 1
        elif c == "'" or c == '"':
            quote = c
            j = i + 1
            while j < n and source[j] != quote:
                j += 1
            if j >= n:
                raise LexError(f"String chưa đóng ở pos {i}")
            tokens.append(Token(TokenType.STRING, source[i + 1 : j], i))
            i = j + 1
        elif c.isdigit() or (c == "-" and i + 1 < n and source[i + 1].isdigit()):
            j = i + 1
            while j < n and (source[j].isdigit() or source[j] == "."):
                j += 1
            tokens.append(Token(TokenType.NUMBER, float(source[i:j]), i))
            i = j
        elif c.isalpha() or c == "_":
            j = i + 1
            while j < n and (source[j].isalnum() or source[j] == "_"):
                j += 1
            word = source[i:j]
            ttype = KEYWORDS.get(word.upper(), TokenType.IDENT)
            tokens.append(Token(ttype, word, i))
            i = j
        else:
            raise LexError(f"Ký tự không hợp lệ '{c}' ở pos {i}")
    tokens.append(Token(TokenType.EOF, None, n))
    return tokens


# ============================================================================
# 4. PARSER — Wernicke proper, recursive descent với precedence
# ============================================================================
class ParseError(SyntaxError):
    pass


class Parser:
    """Grammar (precedence thấp → cao):
       expr     ::= or_expr
       or_expr  ::= and_expr ('OR' and_expr)*
       and_expr ::= not_expr ('AND' not_expr)*
       not_expr ::= 'NOT' not_expr | compare
       compare  ::= primary (('<' | '=') primary)?
       primary  ::= NUMBER | STRING | IDENT | '(' expr ')'
    """

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _consume(self, ttype: TokenType) -> Token:
        tok = self._peek()
        if tok.type != ttype:
            raise ParseError(
                f"Mong {ttype.value}, gặp {tok.type.value}('{tok.value}') ở pos {tok.pos}"
            )
        self.pos += 1
        return tok

    def parse(self) -> Expr:
        ast = self._or_expr()
        if self._peek().type != TokenType.EOF:
            tok = self._peek()
            raise ParseError(f"Token thừa '{tok.value}' ở pos {tok.pos}")
        return ast

    def _or_expr(self) -> Expr:
        left = self._and_expr()
        while self._peek().type == TokenType.OR:
            self._consume(TokenType.OR)
            right = self._and_expr()
            left = Or(left, right)
        return left

    def _and_expr(self) -> Expr:
        left = self._not_expr()
        while self._peek().type == TokenType.AND:
            self._consume(TokenType.AND)
            right = self._not_expr()
            left = And(left, right)
        return left

    def _not_expr(self) -> Expr:
        if self._peek().type == TokenType.NOT:
            self._consume(TokenType.NOT)
            return Not(self._not_expr())
        return self._compare()

    def _compare(self) -> Expr:
        left = self._primary()
        if self._peek().type == TokenType.LESS:
            self._consume(TokenType.LESS)
            return Less(left, self._primary())
        if self._peek().type == TokenType.EQUAL:
            self._consume(TokenType.EQUAL)
            return Equal(left, self._primary())
        return left

    def _primary(self) -> Expr:
        tok = self._peek()
        if tok.type == TokenType.NUMBER:
            self._consume(TokenType.NUMBER)
            return NumLit(tok.value)
        if tok.type == TokenType.STRING:
            self._consume(TokenType.STRING)
            return StrLit(tok.value)
        if tok.type == TokenType.IDENT:
            self._consume(TokenType.IDENT)
            # 'true'/'false' → BoolLit, còn lại → VarRef
            if tok.value.lower() == "true":
                return BoolLit(True)
            if tok.value.lower() == "false":
                return BoolLit(False)
            return VarRef(tok.value)
        if tok.type == TokenType.LPAREN:
            self._consume(TokenType.LPAREN)
            inner = self._or_expr()
            self._consume(TokenType.RPAREN)
            return inner
        raise ParseError(f"Mong primary, gặp {tok.type.value}('{tok.value}') ở pos {tok.pos}")


def parse(source: str) -> Expr:
    return Parser(tokenize(source)).parse()


# ============================================================================
# 5. VISITORS — operations trên AST không đụng vào AST classes
# ============================================================================
class Visitor(ABC):
    @abstractmethod
    def visit_num(self, n: NumLit) -> Any: ...
    @abstractmethod
    def visit_str(self, n: StrLit) -> Any: ...
    @abstractmethod
    def visit_bool(self, n: BoolLit) -> Any: ...
    @abstractmethod
    def visit_var(self, n: VarRef) -> Any: ...
    @abstractmethod
    def visit_and(self, n: And) -> Any: ...
    @abstractmethod
    def visit_or(self, n: Or) -> Any: ...
    @abstractmethod
    def visit_not(self, n: Not) -> Any: ...
    @abstractmethod
    def visit_less(self, n: Less) -> Any: ...
    @abstractmethod
    def visit_equal(self, n: Equal) -> Any: ...


class PrettyPrintVisitor(Visitor):
    """In AST với indent + cây."""

    def __init__(self):
        self.depth = 0

    def _indent(self) -> str:
        return "  " * self.depth

    def visit_num(self, n: NumLit) -> str:
        return f"{self._indent()}NumLit({n.value})"

    def visit_str(self, n: StrLit) -> str:
        return f"{self._indent()}StrLit('{n.value}')"

    def visit_bool(self, n: BoolLit) -> str:
        return f"{self._indent()}BoolLit({n.value})"

    def visit_var(self, n: VarRef) -> str:
        return f"{self._indent()}VarRef({n.name})"

    def _binop(self, name: str, left: Expr, right: Expr) -> str:
        head = f"{self._indent()}{name}"
        self.depth += 1
        l = left.accept(self)
        r = right.accept(self)
        self.depth -= 1
        return f"{head}\n{l}\n{r}"

    def visit_and(self, n: And) -> str:
        return self._binop("And", n.left, n.right)

    def visit_or(self, n: Or) -> str:
        return self._binop("Or", n.left, n.right)

    def visit_not(self, n: Not) -> str:
        head = f"{self._indent()}Not"
        self.depth += 1
        inner = n.inner.accept(self)
        self.depth -= 1
        return f"{head}\n{inner}"

    def visit_less(self, n: Less) -> str:
        return self._binop("Less", n.left, n.right)

    def visit_equal(self, n: Equal) -> str:
        return self._binop("Equal", n.left, n.right)


class ToSQLVisitor(Visitor):
    """Compile AST → SQL WHERE fragment.
    Lưu ý: dùng parameter binding thật trong production để chống SQL injection.
    Ở đây inline string cho demo dễ đọc."""

    def visit_num(self, n: NumLit) -> str:
        return str(n.value)

    def visit_str(self, n: StrLit) -> str:
        # escape quote — production: dùng prepared statement
        return "'" + n.value.replace("'", "''") + "'"

    def visit_bool(self, n: BoolLit) -> str:
        return "TRUE" if n.value else "FALSE"

    def visit_var(self, n: VarRef) -> str:
        return n.name  # production: whitelist column name

    def visit_and(self, n: And) -> str:
        return f"({n.left.accept(self)} AND {n.right.accept(self)})"

    def visit_or(self, n: Or) -> str:
        return f"({n.left.accept(self)} OR {n.right.accept(self)})"

    def visit_not(self, n: Not) -> str:
        return f"(NOT {n.inner.accept(self)})"

    def visit_less(self, n: Less) -> str:
        return f"({n.left.accept(self)} < {n.right.accept(self)})"

    def visit_equal(self, n: Equal) -> str:
        return f"({n.left.accept(self)} = {n.right.accept(self)})"


# ============================================================================
# 6. VÍ DỤ 1 — Boolean expression eval
# ============================================================================
def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def demo_boolean_eval():
    section("Demo 1 — Boolean expression eval (neural conditions)")
    sources = [
        "spike AND threshold",
        "(spike AND threshold) OR refractory",
        "NOT (refractory AND fatigue)",
        "spike AND NOT refractory",
    ]
    contexts = [
        Context({"spike": True, "threshold": True, "refractory": False, "fatigue": False}),
        Context({"spike": True, "threshold": False, "refractory": True, "fatigue": False}),
    ]
    for src in sources:
        ast = parse(src)
        print(f"\n  source: {src!r}")
        print(f"  AST:")
        for line in ast.accept(PrettyPrintVisitor()).splitlines():
            print(f"    {line}")
        for i, ctx in enumerate(contexts):
            print(f"  ctx{i + 1} = {ctx._vars}  →  {ast.interpret(ctx)}")


# ============================================================================
# 7. VÍ DỤ 2 — Hỏng / thiếu: parse error, name error, type error
# ============================================================================
def demo_failure_modes():
    section("Demo 2 — 3 failure modes của Interpreter")

    # 2a — Parse error
    print("\n[2a] Parse error: thiếu RPAREN")
    try:
        parse("(spike AND threshold")
    except ParseError as e:
        print(f"  ✓ ParseError: {e}")

    print("\n[2a'] Lex error: ký tự lạ")
    try:
        parse("spike AND threshold @")
    except LexError as e:
        print(f"  ✓ LexError: {e}")

    # 2b — Name error (semantic lookup fail — analog Wernicke aphasia)
    print("\n[2b] Name error: biến chưa định nghĩa (Wernicke aphasia analog)")
    ast = parse("spike AND unknown_var")
    try:
        ast.interpret(Context({"spike": True}))
    except NameError as e:
        print(f"  ✓ NameError: {e}")

    # 2c — Type error
    print("\n[2c] Type error: AND yêu cầu bool")
    ast = parse("spike AND count")
    try:
        ast.interpret(Context({"spike": True, "count": 5}))
    except TypeError as e:
        print(f"  ✓ TypeError: {e}")

    print("\n[2d] Type error: < yêu cầu số")
    ast = parse("name < 3")
    try:
        ast.interpret(Context({"name": "Alice"}))
    except TypeError as e:
        print(f"  ✓ TypeError: {e}")


# ============================================================================
# 8. VÍ DỤ 3 — Ellumm Lesson Query DSL
# ============================================================================
@dataclass
class Lesson:
    id: int
    pattern: str
    category: str
    difficulty: float
    has_neuro: bool


def demo_ellumm_lesson_query():
    section("Demo 3 — Ellumm Lesson Query DSL (1 AST, 3 operations)")

    lessons = [
        Lesson(1, "Singleton", "Creational", difficulty=2, has_neuro=True),
        Lesson(2, "Builder", "Creational", difficulty=4, has_neuro=True),
        Lesson(3, "Adapter", "Structural", difficulty=2, has_neuro=True),
        Lesson(4, "Decorator", "Structural", difficulty=3, has_neuro=True),
        Lesson(5, "Iterator", "Behavioral", difficulty=3, has_neuro=True),
        Lesson(6, "Visitor", "Behavioral", difficulty=5, has_neuro=False),
    ]

    queries = [
        "category = 'Creational' AND difficulty < 3",
        "(category = 'Behavioral' OR category = 'Structural') AND has_neuro",
        "NOT (difficulty < 4)",
    ]

    for q in queries:
        print(f"\n  Query: {q!r}")
        ast = parse(q)

        # Operation 1: pretty print
        print("  PRETTY:")
        for line in ast.accept(PrettyPrintVisitor()).splitlines():
            print(f"    {line}")

        # Operation 2: eval trên Python list
        matched = [l for l in lessons if _eval_lesson(ast, l)]
        print("  MATCHED:", [f"#{l.id} {l.pattern}" for l in matched])

        # Operation 3: compile sang SQL
        sql = ast.accept(ToSQLVisitor())
        print(f"  SQL:    SELECT * FROM lessons WHERE {sql}")


def _eval_lesson(ast: Expr, l: Lesson) -> bool:
    ctx = Context({
        "id": l.id,
        "pattern": l.pattern,
        "category": l.category,
        "difficulty": l.difficulty,
        "has_neuro": l.has_neuro,
    })
    return bool(ast.interpret(ctx))


# ============================================================================
# 9. DEMO 4 — Cùng AST, nhiều Context (insight architect)
# ============================================================================
def demo_one_ast_many_contexts():
    section("Demo 4 — Một AST, nhiều Context (cache + reuse)")
    ast = parse("threshold < value AND NOT silenced")
    print(f"\n  AST parsed một lần, eval trên 4 neuron khác nhau:")
    neurons = [
        {"threshold": 0.5, "value": 0.8, "silenced": False, "name": "N1 fires"},
        {"threshold": 0.5, "value": 0.3, "silenced": False, "name": "N2 quiet"},
        {"threshold": 0.5, "value": 0.9, "silenced": True, "name": "N3 silenced"},
        {"threshold": 0.5, "value": 0.6, "silenced": False, "name": "N4 fires"},
    ]
    for n in neurons:
        name = n.pop("name")
        result = ast.interpret(Context(n))
        print(f"    {name}: {result}")


def main():
    demo_boolean_eval()
    demo_failure_modes()
    demo_ellumm_lesson_query()
    demo_one_ast_many_contexts()
    print("\n" + "=" * 70)
    print("  Hết demo Lesson 15 — Interpreter (Wernicke).")
    print("=" * 70)


if __name__ == "__main__":
    main()
