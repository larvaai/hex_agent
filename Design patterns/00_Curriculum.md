# Lộ trình 23 Design Patterns (GoF) qua lăng kính Neuroscience

Mục tiêu: tư duy của một software architect — biết **khi nào** dùng pattern nào, **tại sao**, và **giá phải trả**.

Mỗi lesson đi theo 3 mức trình bày Ellumm:
1. **Concept** (ý tưởng): vấn đề pattern giải quyết, neuroscience analogy.
2. **Algorithm** (thuật toán): logic vận hành, biến số, luồng điều khiển.
3. **Pseudocode + Python**: cài đặt thực tế chạy được.

Mỗi pattern bao phủ 5 chiều: cấu tạo, vị trí, chức năng, kết nối, ý nghĩa — kèm 3 loại ví dụ: vận hành thường, hỏng/thiếu, ứng dụng Ellumm.

---

## I. CREATIONAL (5) — Cách tạo object

| #  | Pattern          | Neuroscience Analogy                                                       |
|----|------------------|----------------------------------------------------------------------------|
| 01 | Singleton        | Locus Coeruleus — 1 nguồn norepinephrine duy nhất cho toàn não             |
| 02 | Factory Method   | Neural stem cell — chọn loại neuron sinh ra dựa vào morphogen              |
| 03 | Abstract Factory | Neurogenesis cortex vs hippocampus — bộ tế bào hỗ trợ khác nhau            |
| 04 | Builder          | Synaptogenesis — lắp dendrite, axon, synapse từng bước                     |
| 05 | Prototype        | Mirror neuron — sao chép mẫu hành động đã có                               |

## II. STRUCTURAL (7) — Cách ghép object

| #  | Pattern    | Neuroscience Analogy                                                              |
|----|------------|-----------------------------------------------------------------------------------|
| 06 | Adapter    | Thalamus — chuyển định dạng signal từ giác quan này sang chuẩn cortex             |
| 07 | Bridge     | Tách "loại signal" (vision/audio) khỏi "kênh dẫn" (parvocellular/magnocellular)   |
| 08 | Composite  | Cortical column — neuron đơn và cụm neuron cùng giao diện                         |
| 09 | Decorator  | Myelin sheath — bọc thêm chức năng (tăng tốc) lên axon gốc                        |
| 10 | Facade     | Brainstem — 1 cổng đơn giản che các hệ tự động phức tạp                           |
| 11 | Flyweight  | Receptor type — 1 GABA-A receptor dùng chung ở hàng tỉ synapse                    |
| 12 | Proxy      | Blood-Brain Barrier — kiểm soát truy cập tới neuron thật                          |

## III. BEHAVIORAL (11) — Cách object tương tác

| #  | Pattern                  | Neuroscience Analogy                                                          |
|----|--------------------------|-------------------------------------------------------------------------------|
| 13 | Chain of Responsibility  | Spinal reflex → brainstem → cortex (escalation pain signal)                   |
| 14 | Command                  | Motor program — đóng gói "lệnh vận động" có thể undo/queue                    |
| 15 | Interpreter              | Wernicke's area — dịch chuỗi âm vị thành nghĩa                                |
| 16 | Iterator                 | Saccade — quét tuần tự từng vùng visual scene                                 |
| 17 | Mediator                 | Thalamus relay — không cho cortex A nói thẳng cortex B                        |
| 18 | Memento                  | Hippocampal episodic snapshot — lưu state để hồi tưởng                        |
| 19 | **Observer**             | **Amygdala salience → insula, HPA, motor cortex cùng react**                  |
| 20 | State                    | Sleep stages (NREM1→2→3→REM) — cùng não, hành vi khác nhau                    |
| 21 | Strategy                 | Dual-route fear: low road (thalamo-amygdala) vs high road (cortex)            |
| 22 | Template Method          | LTP protocol — khung cố định, chi tiết cơ chế thay đổi theo synapse           |
| 23 | Visitor                  | Microglial scan — đi qua từng neuron, hành xử khác theo loại                  |

---

## Quy ước thư mục

```
D:\Claude code\Design patterns\
├── 00_Curriculum.md            ← file này
├── 01_Singleton\
│   ├── 01_Singleton.md         ← lesson
│   └── 01_singleton.py         ← code chạy được
├── 02_FactoryMethod\
│   └── ...
└── ...
```

Học xong 23 pattern, bước tiếp theo là **anti-patterns + SOLID + nguyên lý kiến trúc** (Clean Architecture, Hexagonal, Event-driven, CQRS) — đó mới là tầng software architect thật sự.
