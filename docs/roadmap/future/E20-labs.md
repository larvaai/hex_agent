# E20 — Labs · `park-with-trigger`

> Living note (roadmap "kho lạnh có nhãn-ngưỡng"). Nguồn: report `roadmap-living-notes` §E20 (bám code thật). Đọc cùng [README.md](../README.md) + [dependency-map.md](../dependency-map.md). `deps 🟢` = *được phép* ≠ *nên*.

## 1. problem_solved
Nơi đặt "tiện ích dùng chung" thử nghiệm (scratchpad, fixtures, harness mock offline, demo tools) đóng gói thành feature-plugin bật/tắt qua config, thay vì rải rác trong core. Tách đồ-chơi khỏi đường găng kernel; cho dev bật bộ "labs" thí nghiệm prompt/role/skill mà vẫn qua đúng chokepoint + safety + observability. *Thùng chứa có kỷ luật, không phải hạ tầng mới.*

## 2. why_not_now
Cơ chế "utility cắm vào kernel" ĐÃ CÓ và đang chạy → chưa có gì để đấu. Loader `features/loader.py:10` đọc config → import → `install(kernel)`; pattern chuẩn hóa quanh `FeatureDescriptor`+`install` (`features/example_echo.py:23`, `features/llm_chat.py:35`, `toolbox/feature.py:27`). 4 feature enabled (`config/features.yaml:1-13`). Thiếu không phải hạ tầng mà là NHU CẦU cụ thể. Cổng ⚪ "sau S5" (`project-roadmap.md` Sprint table), mà S4/S5 chưa bắt đầu.

## 3. current_anchors (verbatim)
- `features/loader.py:10` — `install_configured_features`.
- `core/schemas.py` `FeatureDescriptor` dùng tại `features/example_echo.py:9-13,23`.
- `toolbox/feature.py:27`, `features/llm_chat.py:35`, `rag/feature.py`.
- `config/features.yaml:1-13` (4 enabled).
- chưa có stub doc / test riêng cho labs.

## 4. wiring_threshold (đo được — cổng-THỜI-ĐIỂM, không phải cổng-hạ-tầng)
- (1) ≥3 utility-feature trùng lặp helper ở ≥2 module `features/*`.
- (2) ≥1 feature "experimental" cần bật dev / tắt mặc định prod (cần profile labs-vs-prod).
- (3) >1 dev cần workspace scratch chung.
- (4) S5 đóng (cổng "sau nền vững" mở).

## 5. wiring_sketch (cực rẻ, seam sẵn)
Tạo `features/labs/`, mỗi tool theo pattern `FeatureDescriptor`+`install` như `features/example_echo.py:23`; đăng ký qua `config/features.yaml` với `enabled:false` mặc định (loader `:14-16` đã honor cờ); nếu cần, overlay `features.labs.yaml` không sửa loader; mọi tool tự qua `execute_tool` (`core/kernel.py:63`) → "mock offline" đạt không cần đường tắt.

## 6. dependencies (cổng)
⚪ cổng-thời-điểm — deps kỹ thuật 🟢 hết (không bị chặn kỹ thuật). Cuối thứ tự rã đông (tầng 5). Định nghĩa "nền vững": cần người dùng chốt (E21 integration xong, hay cả cụm P4 done?).

## 7. critique (YAGNI · risks-built · risks-skipped)
Nhiều khả năng KHÔNG cần như epic. Mọi thứ E20 hứa đã làm được hôm nay: thêm 1 file vào `features/` + bật config. Không mở khoá năng lực mới — chỉ là CÁI TÊN/THƯ MỤC. YAGNI điển hình.
- **Build sớm** = cám dỗ xây "labs runtime/registry" song song loader → trùng đường nạp + nguy cơ đường tắt vòng qua chokepoint (thủng safety).
- **Bỏ hẳn** = gần như không mất gì; rủi ro duy nhất (feature thử nghiệm bật nhầm prod) giải bằng quy ước `enabled:false` + profile, 1 PR nhỏ.

## 8. verdict
`park-with-trigger`. Tầng rã đông: **5 (cuối)** — khi chạm: thêm `features/labs/` + entry config `enabled:false`. Không dựng subsystem song song.
