# Nhật ký rà nhãn của tác giả

Ngày rà: 13/11/2026. Người rà: Nguyễn Thị Thu Hà.

**Phạm vi: 38 trên 38 nhãn** (20 coherence + 18 grounding). **Kết quả: giữ nguyên cả 38 nhãn, không đổi nhãn nào**, nên mọi số liệu không thay đổi.

**Cách rà:** tài liệu gốc bằng tiếng Anh; tác giả rà dựa trên bản dịch ý sang tiếng Việt của từng chunk (nêu nội dung, chỗ bị cụt đầu/cuối, nhãn và lý do của Claude) do Claude cung cấp trong khung chat, không đọc nguyên văn tiếng Anh. Tác giả thấy nhãn của Claude trước khi quyết định (có nguy cơ bị neo theo nhãn có sẵn). Mỗi lần trả lời "ok" hoặc nêu nhãn muốn đổi.

**Sáu nhãn khó/biên được hỏi riêng từng dòng trước:**

| Nhãn | Nhãn của Claude | Quyết định của tác giả |
|---|---|---|
| Coherence P02-B | 2 | giữ 2 |
| Coherence P04-B | 1 | giữ 1 |
| Grounding B-T06 | 2 | giữ 2 |
| Grounding C-T06 | 1 | giữ 1 |
| Grounding A-T05 | 1 | giữ 1 (lúc đầu chọn 0 nhưng là bấm nhầm, tác giả xác nhận không đổi) |
| Grounding B-T04 | 2 | lúc đầu chọn 1 (đáp án ở hạng 2), sau khi chốt quy tắc dưới đây thì giữ 2 |

32 nhãn còn lại được rà theo từng nhóm (cùng vị trí coherence hoặc cùng câu hỏi grounding); tác giả trả lời "ok" cho tất cả.

**Quy tắc chốt (thang grounding):** đáp án nằm ở hạng nào trong top-3 cũng được, miễn top-3 đủ ý chính (không bắt buộc hạng 1).

**Sửa của Claude:** lý do của Coherence P05-B ghi nhầm "bị cắt ở dòng output"; thực tế chunk kết thúc ở hết khối code. Đã sửa chữ trong cột `reason`, nhãn giữ nguyên; tác giả được báo về chỗ sửa này trước khi duyệt dòng đó.
