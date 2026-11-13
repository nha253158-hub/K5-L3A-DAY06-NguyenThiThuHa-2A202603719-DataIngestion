# Tiêu chí chọn chiến lược (chốt TRƯỚC khi chạy truy xuất và trước khi xem test)

Thứ tự ưu tiên, chỉ dùng DEV (16 câu) và các nhãn không phụ thuộc test để chọn:

1. **Evidence Hit@3 trên dev** (n/16) cao hơn. Chênh lệch ≤ 1 câu được coi là hòa (mẫu quá nhỏ).
2. Nếu hòa: **Hit@1 trên dev** cao hơn; chênh lệch ≤ 1 câu vẫn coi là hòa.
3. Nếu vẫn hòa: **chunk coherence trung bình /2** trên cùng 10 vị trí nguồn (chọn theo quy tắc cố định, không phụ thuộc điểm truy xuất).
4. Nếu vẫn hòa: chiến lược **rẻ hơn** (ít chunk hơn, thời gian ingest ngắn hơn).

Quy tắc riêng cho B so với C (chỉ khác nhau ở filter):

* C được ưu tiên hơn B chỉ khi trên các câu filter của dev (D14, D15) C không tệ hơn B ở Hit@3 **và** top-3 của C tuân thủ filter ở 100% câu filter. Điều kiện áp dụng: chỉ khi người dùng/ngữ cảnh cung cấp giá trị filter trước khi truy xuất.
* Nếu filter không đổi kết quả trên dev, ghi nhận "không có bằng chứng filter giúp" thay vì suy ra có lợi.

Test (6 câu) chỉ để báo cáo một lần sau khi đã chọn; không dùng để chỉnh tham số chunk hay filter. Mọi chỉnh sửa sau khi xem test (nếu có) phải được ghi rõ trong báo cáo và không được coi là kiểm tra độc lập.

Tham số chunk của A (500/50) và B (target 600, max 1000, min 120) được cố định trước khi chạy; không có vòng tuning nào trên dev hoặc test.
