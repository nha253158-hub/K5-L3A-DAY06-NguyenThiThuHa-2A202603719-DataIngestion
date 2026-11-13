# Thang chấm grounding (viết cùng lúc gán nhãn, sau khi đã xem top-3; không phải tiêu chí chốt trước)

Với mỗi (cấu hình, câu test), chỉ nhìn top-3 chunk được trả về và `expected_answer`:

- **2** — top-3 chứa đủ ý chính của đáp án mong đợi; một người chỉ đọc 3 chunk này có thể trả lời đúng (không nhất thiết đúng trang gold hay đúng rank 1).
- **1** — top-3 liên quan nhưng thiếu ý chính hoặc ý chính bị cắt/tách giữa các chunk.
- **0** — top-3 không đủ để trả lời hoặc lạc đề.

Người chấm: Claude (LLM) chấm sơ bộ, tác giả rà lại (cột `reviewed_by_author`). Grounding **không** đồng nhất với Evidence Hit@3: Hit@3 chỉ tính trang gold và câu evidence nguyên vẹn, grounding chấp nhận bằng chứng tương đương ở trang khác (ví dụ B–T06).
