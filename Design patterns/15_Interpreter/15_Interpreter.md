# Lesson 15 — Interpreter Pattern
## Wernicke's Area — Dịch chuỗi âm vị thành nghĩa

---

## TÓM TẮT MỘT DÒNG

**Interpreter** = định nghĩa grammar cho 1 ngôn ngữ con, đại diện mỗi rule grammar bằng 1 class, ghép thành cây (AST) để mỗi node tự "interpret" mình — thêm rule mới = thêm class, không sửa interpreter chính.

> Khi bạn nghe ai đó nói "tôi muốn lọc bài học pattern Creational khó dưới 3", phonemes tới A1 → STG → **Wernicke's area** parse phoneme → morpheme → word → phrase → meaning. Wernicke không "ép buộc một cách hiểu duy nhất" — nó dựng cây cú pháp, gắn từng node vào semantic memory, rồi rút ra hành động cần làm. Đó chính là Interpreter pattern: AST + walk + context lookup.

---

## MỨC 1 — CONCEPT

### 1.1. Vấn đề pattern giải quyết

Khi cần xử lý input có cấu trúc — DSL (domain-specific language), filter expression, boolean rule, query language, regex, math expression — bạn có 3 lựa chọn:

1. **Hard-code if/else**: viết regex thủ công, parse bằng `split` và `==`. Nhanh cho 5 rule đầu, sau đó phình to mất kiểm soát, không compose được, mỗi rule mới phải sửa core logic (vi phạm Open/Closed).
2. **Parser generator** (ANTLR, Lark, PLY): mạnh, đúng cho ngôn ngữ lớn (SQL, ngôn ngữ lập trình). Overkill cho DSL có 5–20 rule. Phức tạp build, học, debug.
3. **Interpreter pattern**: mỗi rule = 1 class, AST = composition của các class này, mỗi class có method `interpret(context)`. Thêm rule = thêm class, không đụng vào core. Vừa đủ cho DSL nhỏ và vừa.

Interpreter là điểm vàng giữa _hardcode_ và _parser-generator_.

### 1.2. Neuroscience analogy — Wernicke's area

**Wernicke's area** (BA22, posterior superior temporal gyrus, hemisphere trái) là vùng hiểu ngôn ngữ — biến phoneme stream thành nghĩa.

Đường đi:
1. Cochlea → A1 (primary auditory cortex): nhận âm thô, phổ tần số.
2. STG (superior temporal gyrus): tách ranh giới phoneme.
3. **Wernicke**: parse phoneme → morpheme → word → phrase → sentence; gắn mỗi đơn vị với semantic memory ở **anterior temporal lobe** (ATL).
4. Arcuate fasciculus → **Broca's area** (BA44/45): syntax + production (nói lại / thực thi lệnh).

Đặc điểm:
- Wernicke **không hiểu duy nhất một câu** — nó dựng cây cú pháp rồi gắn nghĩa qua context. "Bank" trong "river bank" vs "bank account" được phân biệt bởi context node ở mức cao hơn.
- **Tổn thương Wernicke → fluent aphasia (Wernicke's aphasia)**: bệnh nhân nói trôi chảy (Broca còn, syntax còn) nhưng câu vô nghĩa (không có interpret/lookup vào semantic memory). _Đó chính là analog của "AST không có context"._
- **Tổn thương Broca → non-fluent aphasia**: hiểu được (Wernicke còn) nhưng nói khó khăn. Tách trách nhiệm Broca/Wernicke = tách Production/Comprehension trong code.

#### 5 chiều của analogy

| Chiều      | Trong não                                                                | Trong code                                                                |
|------------|--------------------------------------------------------------------------|---------------------------------------------------------------------------|
| Cấu tạo    | BA22 + STG + arcuate fasciculus + ATL (semantic memory)                  | AbstractExpression + Terminal + NonTerminal + Context + Visitor (option) |
| Vị trí     | Sau auditory cortex, trước motor language area                           | Tách khỏi Lexer (input) và Executor (output side effect)                  |
| Chức năng  | Parse phoneme → AST → bind nghĩa từ context (ATL)                        | Parse token → AST → interpret(context) trả value/action                   |
| Kết nối    | A1 → STG → Wernicke ↔ ATL ↔ Broca                                       | Lexer → Parser → AST → Interpreter ↔ Context ↔ Action layer              |
| Ý nghĩa    | Cùng phoneme stream, nhiều nghĩa khác nhau theo context                  | Cùng AST, eval nhiều lần với Context khác nhau (testable, reusable)       |

### 1.3. Khi nào DÙNG

- DSL nhỏ–vừa: filter language, query language, boolean rule engine, validation expressions, calculator, template engine.
- Grammar **ổn định** — không đổi cấu trúc lớn theo runtime.
- Cần **inspect / serialize / optimize** AST trước khi eval (constant folding, pretty-print, type-check).
- Cần eval **cùng AST với nhiều Context khác nhau** — ví dụ: 1 query, chạy trên 10 user, mỗi user có data riêng.
- Cần **plug-in rule engine**: cho user định nghĩa logic ngoài code (config-driven).

### 1.4. Khi nào KHÔNG DÙNG

- Grammar phức tạp: operator precedence chồng chéo, ambiguity, left-recursion → dùng parser generator (Lark, ANTLR).
- Performance critical: walk AST chậm hơn bytecode; ngôn ngữ chạy hàng triệu lần/giây thì compile xuống bytecode hoặc native code (LLVM, ProtoBuf).
- Grammar thay đổi runtime nhiều: Interpreter cứng theo class — khó hot-reload. Dùng **rule engine** dữ liệu hoá hoặc **embedded scripting** (Lua, Python eval với sandbox).
- Khi đã có sẵn library/protocol chuẩn (SQL, JSONLogic, MongoDB query) — **đừng tự dựng DSL**.

### 1.5. Cảnh báo architect

> **DSL là khoản nợ kỹ thuật ngầm**. Mỗi DSL tự dựng = 1 ngôn ngữ user phải học, team phải maintain, không có IDE support, không có syntax highlighting, không có format. Trước khi viết Interpreter, hỏi: _có thể dùng JSON/YAML thay không?_ — nếu có thì AST chính là JSON object, "interpreter" chỉ còn là pattern-matching trên dict. Đơn giản hơn nhiều.

---

## MỨC 2 — ALGORITHM

### 2.1. Vai diễn

```
                ┌──────────────────────┐
                │ AbstractExpression   │
                │  + interpret(ctx)→T  │
                └──────────────────────┘
                        △
        ┌───────────────┴────────────────┐
        │                                │
┌──────────────────┐           ┌─────────────────────┐
│ TerminalExpr     │           │ NonTerminalExpr     │
│ (NumLit,         │           │ (And, Or, Not,      │
│  VarRef,         │           │  Greater, Equal,    │
│  StringLit)      │           │  WhereClause)       │
│                  │           │                     │
│ + interpret(ctx) │           │ children: list[Expr]│
└──────────────────┘           │ + interpret(ctx)    │
                               └─────────────────────┘

┌──────────────────────┐         ┌──────────────────────┐
│      Context         │◀────────│      Lexer           │
│ - vars: dict         │         │   tokens(input)      │
│ - lexicon: dict      │         └──────────────────────┘
│ - semantic_memory    │
└──────────────────────┘                  │
            ▲                             ▼
            │                  ┌──────────────────────┐
            └──────────────────│       Parser         │
                               │   build AST(tokens)  │
                               └──────────────────────┘
```

- **AbstractExpression**: interface định nghĩa `interpret(ctx) -> T`. Tất cả node trong AST đều thực hiện interface này.
- **TerminalExpression** (lá): `NumLit(5)`, `StringLit("creational")`, `VarRef("difficulty")`. Trả thẳng giá trị.
- **NonTerminalExpression** (composite): `And(left, right)`, `Greater(left, right)`. Gọi `left.interpret(ctx)` + `right.interpret(ctx)`, kết hợp.
- **Context**: dict-like — biến (var → value), lexicon (token → meaning), semantic memory (kiểu data type).
- **Lexer (tokenizer)**: input string → list of tokens. _Đây là analog của STG, không phải Wernicke._
- **Parser**: tokens → AST. Wernicke proper.
- **Client**: build AST hoặc gọi parser, rồi `root.interpret(context)`.

### 2.2. Luồng điều khiển

```
"difficulty < 3 AND pattern = 'Creational'"
            │
            ▼ Lexer (STG)
[difficulty][<][3][AND][pattern][=]['Creational']
            │
            ▼ Parser (Wernicke)
                And
               /   \
          Less     Equal
          /  \     /   \
   VarRef  Num  VarRef  StringLit
   (diff)  (3)  (patt)  (Creational)
            │
            ▼ Interpreter walk + Context
And.interpret(ctx)
  ├─ Less.interpret(ctx)
  │   ├─ VarRef("difficulty").interpret(ctx) → 2
  │   ├─ NumLit(3).interpret(ctx) → 3
  │   └─ 2 < 3 → True
  ├─ Equal.interpret(ctx)
  │   ├─ VarRef("pattern").interpret(ctx) → "Creational"
  │   ├─ StringLit("Creational") → "Creational"
  │   └─ True
  └─ True AND True → True
```

### 2.3. Biến trạng thái và bất biến

- AST **nên immutable**: cùng AST có thể eval song song, cache hash, optimize không sợ rò rỉ.
- Context **mutable trong scope một eval**: ví dụ `let x = 5 in x * 2` — `x` chỉ tồn tại trong nhánh đó. Triển khai = stack of dict (scope frames).
- `interpret` **nên là pure function của (AST node, ctx)**: không side-effect ngầm. Nếu cần hành động (DB write, network), tách ra 2 pha:
  1. **Plan phase**: AST → list of intended actions.
  2. **Execute phase**: thực thi list (có thể dry-run, audit log, undo).

### 2.4. Biến thể

| Biến thể | Mô tả | Khi nào dùng |
|----------|-------|--------------|
| **Tree-walking interpreter** | Mỗi node có `interpret`, walk recursive | DSL nhỏ–vừa, đơn giản |
| **Visitor + AST passive** | AST chỉ là data, operation ở Visitor (eval, print, type-check) | Có nhiều op trên cùng AST — Visitor mạnh ở đây |
| **Bytecode VM** | Compile AST → opcodes → eval VM loop | Cần performance |
| **Partial evaluation / specialization** | Eval pre-AST với Context biết trước → AST tinh giản | Khi cùng query chạy nhiều lần với cùng config |
| **JIT compile** | Compile xuống native | Hot path, ví dụ regex, query engine của DB |

> **Quy tắc architect**: bắt đầu bằng tree-walking. Khi cần thêm op (print, optimize, type-check) → chuyển sang Visitor + AST passive. Khi đo được bottleneck → bytecode VM. Đừng compile sớm.

### 2.5. Flyweight cho TerminalExpression

Cùng `NumLit(0)` xuất hiện 1000 lần trong AST → cache 1 instance dùng chung (Flyweight). Tiết kiệm memory đáng kể với DSL có nhiều literal lặp lại. Áp dụng được vì TerminalExpression immutable.

---

## MỨC 3 — PSEUDOCODE + PYTHON

### 3.1. Pseudocode

```
abstract class Expr:
    abstract interpret(ctx: Context) -> Value

class NumLit(Expr):
    value: number
    interpret(ctx) -> value

class VarRef(Expr):
    name: string
    interpret(ctx) -> ctx.lookup(name)

class And(Expr):
    left, right: Expr
    interpret(ctx) -> left.interpret(ctx) AND right.interpret(ctx)

class Less(Expr):
    left, right: Expr
    interpret(ctx) -> left.interpret(ctx) < right.interpret(ctx)

# Lexer: string → tokens
# Parser: tokens → AST (recursive descent với precedence)
# Client: ast = parse("difficulty < 3 AND pattern = 'Creational'")
#         result = ast.interpret(Context(vars={"difficulty": 2, "pattern": "Creational"}))
```

### 3.2. Python — 3 ví dụ

Code đầy đủ ở `15_interpreter.py`. Tóm tắt 3 demo:

#### Ví dụ 1 — Vận hành thường: Boolean expression eval

DSL boolean cho neural conditions:
```
"(spike AND threshold) OR refractory"
"NOT (refractory AND fatigue)"
```
Tokenizer + Parser + AST + interpret. AST in ra cây bằng Visitor pretty-print.

Điểm cần chú ý của architect:
- Parser dùng **recursive descent** với operator precedence (`OR` < `AND` < `NOT`).
- AST node **frozen dataclass** → immutable, hashable, có thể cache.
- **Context** là dict đơn giản — phù hợp DSL nhỏ.

#### Ví dụ 2 — Hỏng / thiếu: Lỗi parse, biến chưa định nghĩa, type mismatch

3 failure mode được handle rõ ràng:
- **Syntax error**: tokenizer hoặc parser raise `ParseError` với vị trí cụ thể.
- **Unknown variable**: interpret raise `NameError` qua Context.
- **Type mismatch**: `"hello" < 3` → raise `TypeError`. Cách architect xử lý: thêm pha **type-check Visitor** chạy trước eval, fail-fast trước khi run.

Bài học: **3 pha rõ rệt** — Lex → Parse → Type-check → Eval. Mỗi pha có error class riêng.

#### Ví dụ 3 — Ứng dụng Ellumm: Lesson Query DSL

User Ellumm muốn search:
```
find lessons WHERE pattern = 'Creational' AND difficulty < 3 OR has_neuro
```

Tách thành:
- `find lessons` — keyword (terminal command)
- `WHERE <expr>` — non-terminal predicate
- `<expr>` — boolean expression cấu trúc trên fields của lesson

Cùng AST có thể:
1. **Eval** trên list lessons → trả filtered list.
2. **Compile xuống SQL WHERE** (Visitor visit_x → SQL fragment).
3. **Print pretty** để user xem lại.

Một AST, nhiều operation = sức mạnh thật của Interpreter + Visitor.

---

## SO SÁNH VỚI PATTERN KHÁC

| Pattern        | Khác biệt với Interpreter                                                                |
|----------------|-------------------------------------------------------------------------------------------|
| **Composite**  | Composite = cấu trúc tree node có cùng interface. Interpreter **dùng** Composite cho AST. AST không phải Interpreter, AST + interpret method mới là. |
| **Visitor**    | Visitor tách operation khỏi AST node. Khi có **nhiều operation** trên cùng AST (eval, print, optimize, type-check, compile) — Visitor thắng Interpreter cổ điển. Interpreter cổ điển = AST node tự có 1 method `interpret`. |
| **Strategy**   | Strategy đổi 1 thuật toán cấp cao. Interpreter ghép nhiều "strategy nhỏ" thành tree. Có thể nói Interpreter = Strategy hierarchical. |
| **Iterator**   | Iterator duyệt collection phẳng. Interpreter walk tree (có cấu trúc đệ quy). Đối lập về cấu trúc. |
| **Command**    | Command đóng gói **một** lệnh. Interpreter parse string thành **cây nhiều lệnh**. Có thể dùng chung: leaf của AST là Command để execute. |

> **Insight architect**: Interpreter + Visitor + Composite là _bộ ba thân thiết_. AST = Composite. Walk + operation = Visitor. Định nghĩa grammar = Interpreter pattern. Khi học sâu compiler / DB query engine, ba pattern này luôn xuất hiện cùng nhau.

---

## ANTI-PATTERNS THƯỜNG GẶP

1. **Stringly-typed AST** — đại diện AST bằng string `"AND(spike,threshold)"`, parse lại mỗi lần eval.
   - Triệu chứng: parse cùng query 1000 lần.
   - Xử lý: parse 1 lần, cache AST. AST là object, không phải string.

2. **AST mutable** — node có setter, "tối ưu" tại chỗ.
   - Triệu chứng: 2 thread eval cùng AST → race condition.
   - Xử lý: AST immutable. Optimize sinh AST mới (functional style).

3. **Lexer + Parser + Interpreter trộn 1 hàm** — một hàm 200 dòng, vừa scan vừa eval.
   - Triệu chứng: thêm rule mới = sửa hàm khổng lồ.
   - Xử lý: tách 3 pha. Lexer → tokens. Parser → AST. Interpreter → result. Mỗi pha test riêng.

4. **DSL không cần thiết** — viết DSL chỉ để filter list 5 rule.
   - Triệu chứng: 500 dòng code DSL cho thứ `filter(lambda x: x.diff < 3 and x.pat == 'C')` xử lý xong.
   - Xử lý: chỉ dựng DSL khi user/non-developer cần viết logic, hoặc khi rule thay đổi runtime.

5. **Eval `eval()` Python để cheat** — `eval(user_input_string)`.
   - Triệu chứng: code injection nguy hiểm.
   - Xử lý: KHÔNG. Tự dựng Interpreter bounded grammar. Đó là toàn bộ lý do Interpreter pattern tồn tại.

6. **Không có error position** — báo "syntax error" mà không nói ở đâu.
   - Triệu chứng: user không debug được DSL.
   - Xử lý: token có `position`. Error class chứa `line/col`. Pretty-print error với caret `^`.

---

## BÀI TẬP

1. **Cơ bản**: Thêm operator `XOR` vào boolean DSL ở ví dụ 1. Yêu cầu: thêm class `Xor` mới, **không sửa** class `And/Or/Not` (Open/Closed). Update parser nhận token `XOR`. Test.

2. **Trung bình**: Viết Visitor `PrettyPrintVisitor` đi qua AST và in ra DSL gốc với indent đẹp:
   ```
   AND
   ├─ <
   │  ├─ var(difficulty)
   │  └─ 3
   └─ =
      ├─ var(pattern)
      └─ "Creational"
   ```
   Sau đó viết `OptimizeVisitor` làm constant folding: `2 + 3` → `5`, `True AND x` → `x`.

3. **Khó (architect)**: Lesson Query DSL ở ví dụ 3 — viết thêm 1 Visitor `ToSQLVisitor` compile AST thành câu SQL `WHERE`:
   ```
   pattern = 'Creational' AND difficulty < 3
   ```
   Cẩn thận: escape string (SQL injection!), map field name từ DSL sang column name. Test với 5 query khác nhau, so sánh kết quả `EvalVisitor.eval(lessons)` ≡ `lessons.filter(SQL)`. Đây là backbone của ORM query builder.

4. **Mở rộng neuro**: Mô phỏng bệnh nhân Wernicke aphasia trong code. Tạo `BrokenContext` luôn raise `SemanticLookupError` — AST parse được (Broca + syntax còn nguyên) nhưng `interpret` fail. Print ra "fluent nonsense" tương tự bệnh nhân thật. Sau đó tạo `BrokenParser` ngược lại (Broca's aphasia): Context lookup ok, nhưng parse fail giữa chừng — partial AST. Cho user thấy bệnh ở đâu trong stack.

---

## PYTHON-NATIVE: `ast` module + operator overloading + risk của `eval`

Python có sẵn `ast` module để parse Python code thành AST. Có thể abuse để làm DSL: parse query thành Python AST rồi walk an toàn (không `eval` raw). Ví dụ thực tế: pandas `df.query("a < 3 and b == 'x'")` chính là làm vậy.

Có thể dùng **operator overloading** để build AST không cần lexer:
```python
e = (Var("difficulty") < Lit(3)) & (Var("pattern") == Lit("Creational"))
# __lt__, __and__, __eq__ trả về AST node
```
SQLAlchemy core, Pandas, PySpark đều dùng kỹ thuật này. **Pros**: type-safe, IDE complete, không cần parser. **Cons**: user phải viết Python (không phải DSL thuần text).

> Quy tắc architect: nếu user là **developer** → cho operator overloading (DSL nội nhúng). Nếu user là **non-developer** (analyst, manager) → cho text DSL với parser. Hai cách dùng chung kỹ thuật AST + Interpreter, chỉ khác đầu vào.

`eval(s)` của Python là cám dỗ — dừng lại. Nó không bounded, code injection đảm bảo. Interpreter pattern tồn tại để **kiểm soát grammar**. Nếu dùng `eval` thì coi như chưa từng học pattern này.

---

## CHECKLIST TRƯỚC KHI MERGE PR DÙNG INTERPRETER

- [ ] AST có immutable không? (frozen dataclass / namedtuple)
- [ ] Lexer / Parser / Interpreter có ở 3 file/module riêng không?
- [ ] Có error class riêng cho từng pha (LexError, ParseError, NameError, TypeError) không?
- [ ] Error có chứa position (line/col) để báo user không?
- [ ] Có test cho parse trip-round (`parse(unparse(ast)) == ast`)?
- [ ] Có Visitor cho pretty-print để debug AST không?
- [ ] Có check operator precedence rõ ràng và test edge case không?
- [ ] DSL có thực sự cần thiết không, hay JSON/YAML đã đủ?
- [ ] Có giới hạn AST depth / size để chống DoS (user viết 1000-cấp expression) không?
- [ ] Có sandbox đủ kín — không để query trigger I/O không dự kiến?

---

## TÓM LẠI BẰNG NEUROSCIENCE

> Wernicke không "hiểu câu" theo nghĩa magic. Nó dựng cây phoneme → morpheme → word → phrase, gắn từng node vào ATL (semantic memory) qua context, rồi gửi sang Broca để thực thi. Đó chính là Interpreter pattern: **parse → AST → walk + context → action**.

> Khi bệnh nhân Wernicke aphasia nói "I went the bicycle the morning the bank" — phoneme stream chạy được, Broca production còn (fluent), nhưng AST không gắn được nghĩa với context (Wernicke hỏng). Trong code, tương đương AST parse OK nhưng `interpret` luôn return `None` vì Context lookup fail. Kết quả: "fluent nonsense".

> Architect học Interpreter là để: tạo DSL nhỏ giúp non-developer viết logic, viết rule engine cho config-driven systems, dựng query builder type-safe (SQLAlchemy/Pandas), và quan trọng nhất — **biết khi nào KHÔNG dùng** Interpreter mà chuyển sang parser generator hoặc bytecode VM. Đó là sự phân biệt giữa coder và architect.

Lesson kế tiếp: **17 — Mediator (Thalamus)** — pattern chống N-to-N coupling, một analog hoàn hảo cho thalamic relay nuclei.
