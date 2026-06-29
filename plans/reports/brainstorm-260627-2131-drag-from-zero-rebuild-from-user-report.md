---
harness_version: 0.0.0-dev
harness_kit_digest: f07daf9079d4993e285d1ab1152617b0268bdf32974d12b616c3b58afa5491ad
harness_schema_version: 1.0
---

# Brainstorm: drag_from_zero — dựng lại từ con số 0, xuất phát từ user

**Ngày:** 2026-06-27 · **Mode:** diverge → converge · **Trạng thái:** đã hội tụ, chờ /hs:plan

## Câu hỏi gốc

Nếu xây lại `drag_from_zero` từ đầu, **bắt đầu từ trải nghiệm user** chứ không từ runtime.
Đây là góc ngược hẳn repo hiện tại — repo hiện tại dựng "sự thật" (event log + verifier code)
trước, UI là consumer sau ([README slice 6b](drag_from_zero/README.md)).

## Mô hình user vẽ ra (4 nhân vật)

| Nhân vật | Vai | Quyền |
|---|---|---|
| **Worker agent** | Mặc định 1 con, kéo thêm theo vai trò khi cần | Phân loại input, tự định task, tự decompose, tự chạy. Kẹt → báo + lý do + xin phép |
| **Supervisor agent** | 1 con toàn cục/phiên | Phán verdict, lý do, quyết retry-hay-fail. **Trọng tài tối cao** |
| **Code gate** | Bằng chứng | Chạy check khách quan (file/test/coverage), nạp cho supervisor làm chứng cứ |
| **User** | Quan sát + can thiệp nhẹ | Pause, sửa tiêu chí/mục tiêu task, sửa subtask, góp ý |

### Vòng đời một lượt

1. Input vào con worker mặc định. Worker phân loại: **câu hỏi thường** → nhả text, xong.
   **Task** → đính một **ô vuông task**.
2. Ô vuông task = `{mục tiêu, tiêu chí done, DAG subtask}`. Subtask **nối tiếp mặc định**;
   song song chỉ khi worker đánh dấu rõ độc lập.
3. Worker chạy từng subtask. Không qua được trong lượt → báo + lý do + **xin phép chạy lại**.
4. Supervisor đọc **artifact thật trên disk + tín hiệu code gate** → phán pass/fail + lý do →
   quyết cho chạy thêm vòng hay đánh FAIL.
5. **Thành công** = artifact thật trên disk + verdict pass. **Thất bại** = ô vuông đỏ + lý do.
6. User pause/sửa bất kỳ lúc nào; kéo thêm agent vào giữa chừng.

## Quyết định kiến trúc bản lề

**DEC: Supervisor LLM là trọng tài verdict tối cao, nhưng phán trên bằng chứng thật
(artifact + code gate), context tách rời worker, cùng model 35B.**

Đây là điểm va với lõi hiện tại. [`verifier.py`](drag_from_zero/dragzero/verifier.py) đang cho
**code** là trọng tài duy nhất: `CHECK_VOCAB` đóng, mọi key dạng verdict bị từ chối khi dựng,
worker không bao giờ viết nổi một verdict xanh. Mô hình mới đưa một **LLM** lên làm trọng tài.

Ba phương án đã cân, đã chọn:

- **A (chọn) — Supervisor LLM tối cao.** Phán được "đúng tinh thần chưa", giải thích người đọc
  được, điều phối retry. Bản chọn là **bản bền**, không phải bản kịch: supervisor **không** phán
  trên lời tự báo của worker mà trên **artifact thật + code gate làm chứng cứ**, và chạy ở
  **context tách rời** nên không thấy "lý lẽ tự biện" của worker.
- **B — Code duy nhất (hiện tại).** Không bịa được nhưng cứng, không có con giám sát user muốn.
- **C — Tách tầng cứng (code là sàn, LLM chỉ hạ không nâng).** Bị loại vì user muốn supervisor
  thực sự cầm quyết định cuối.

**Vì sao A-bền vẫn giữ được luật propose/adjudicate split** ([memory](/Users/uspro/.claude/projects/-Users-uspro-Desktop-namnson-hex-agent/memory/hex-agent-lessons-to-carry.md)):
worker **propose** (việc + cấu trúc task), supervisor **adjudicate**. Adjudicator giờ là LLM,
nhưng vì (a) context riêng, (b) phán trên disk thật + code gate, nên nó không chia sẻ động cơ
"khai khống xong" của worker. Split sống, chỉ đổi chất liệu trọng tài từ code sang LLM-có-chứng-cứ.

## Rủi ro (đã nói thẳng với user, user vẫn chọn A)

1. **35B bịa verdict xanh.** Trọng tài là LLM thì verdict có thể sai kể cả khi có chứng cứ —
   supervisor đọc artifact rồi vẫn gật bừa. Code gate hạ rủi ro chứ không xóa.
   *Guard tối thiểu:* khi code gate trả FAIL khách quan (test đỏ, file thiếu), supervisor PASS
   phải bị đánh dấu **mâu thuẫn** và log lại — để đo tần suất 35B chống lại chứng cứ cứng.
2. **1 supervisor toàn cục thành nút cổ chai** khi cây to: mọi node đều chờ một con phán. Chấp
   nhận được lúc đầu (user: "không phức tạp ngay bây giờ"), nhưng pin lại điểm này khi cây sâu.
3. **Mất tính tái lập của eval.** Verdict do LLM thì test harness không còn deterministic ở tầng
   verdict. Cần tách: invariant test (harness, deterministic) vs eval (verdict, scored nhiều lần).

## Delta so với repo hiện tại

| Bộ phận | Hiện tại | Bản re-build |
|---|---|---|
| Trọng tài verdict | code (`verifier.py`) | **supervisor LLM** trên chứng cứ code |
| Điểm vào | dựng topology trước | **1 worker mặc định**, kéo thả sau |
| Phân loại task | luôn là task | worker **tự phân loại** hỏi-vs-task |
| Vai supervisor | không có (code làm) | **nhân vật hạng nhất** |
| Decompose | code accept (`accept.py`) | worker tự chẻ, supervisor nghiệm thu |
| User | author topology | **quan sát + can thiệp nhẹ** |

Giữ lại nguyên: event log là nguồn sự thật, UI là projection, code gate (đổi vai từ trọng tài
thành cung cấp chứng cứ), capability token, ledger disk-truth.

## Câu hỏi mở (chưa chốt, để dành cho /hs:plan)

1. Code gate đổi vai từ "trọng tài" sang "cung cấp chứng cứ cho supervisor" — `verifier.py` tái
   dùng được bao nhiêu, hay viết lại?
2. Supervisor "chỉ hạ không nâng" so với code gate — có ép luật cứng này không, hay để LLM tự do
   hoàn toàn (kể cả nâng FAIL → PASS)? Rủi ro #1 phụ thuộc câu này.
3. Slice đầu tiên của bản re-build là gì? Đề xuất: **worker phân loại hỏi-vs-task + đính ô vuông
   task** (nhỏ nhất, chạm đúng điểm vào user mô tả), supervisor + decompose là slice sau.
4. UI: dựng mới từ user-flow này hay sửa `ui/Agent IDE.dc.html` đang có?
