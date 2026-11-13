# Báo cáo cá nhân — Day 6

Nguyễn Thị Thu Hà · MSSV 2A202603719 · L3A · Repo: https://github.com/nha253158-hub/K5-L3A-DAY06-NguyenThiThuHa-2A202603719-DataIngestion

> Số liệu trong báo cáo lấy từ `results/metrics.csv`, `results/summary.json`, `results/aspects_summary.json`, `results/ingest_stats_{A,B}.json`, `results/run_meta.json` và các trace `results/traces_{A,B,C}.jsonl`. `python3 -I src/summarize_results.py` tạo lại `results/summary.json` từ trace và nhãn.

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền, số trang và quy tắc tính trang**
  - Chủ đề: tài liệu kỹ thuật mở, scikit-learn 1.9.1 User Guide (`doc/modules/*.rst`). Giấy phép BSD-3-Clause, được phép dùng và phân phối kèm thông báo bản quyền (`data/raw/COPYING`).
  - Nguồn tải: `raw.githubusercontent.com`, tag 1.9.1. `data/fetch_log.csv` ghi URL và thời điểm truy cập, `data/manifest.csv` ghi nguồn, quyền, thời điểm truy cập, page ID và số ký tự.
  - Quy tắc tính trang: tài liệu RST không có phân trang. Một trang là một đơn vị liên tục bắt đầu ở tiêu đề mục cấp ≤ 3 và có ≥ 1.500 ký tự sau chuẩn hóa. Mục ngắn hơn được gộp vào đơn vị trước, không bỏ nội dung.
  - Kết quả: 42 tài liệu module được tải, 40 được giữ, 2 bị loại vì tổng < 1.500 ký tự (`isotonic` 872, `unsupervised_reduction` 1.221). Có **288 trang**, 886.780 ký tự, trang ngắn nhất 1.505 và dài nhất 16.794 ký tự (`results/corpus_stats.json`).
- **Chuẩn hóa, lỗi và giới hạn**
  - Chuẩn hóa RST → văn bản thuần bằng regex, không dùng Sphinx: bỏ directive, đổi role/link/nhấn mạnh về chữ thường, bỏ viền bảng, đổi tham chiếu gallery thành `(example: tên)`.
  - Lỗi và giới hạn còn lại: hình/figure bị bỏ; bảng grid chỉ còn văn bản thô; còn 9 chuỗi `**` và 4 dấu backtick lạc. Số liệu theo từng tài liệu ở `results/normalization_log.csv`.
- **Embedding, vector store, lệnh chạy, chi phí**
  - Embedding: `intfloat/multilingual-e5-small`, chạy local trên CPU bằng sentence-transformers 6.3.0 (torch 2.15.0, transformers 5.22.2), 384 chiều, revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`. Dùng tiền tố `passage: ` và `query: `, vector chuẩn hóa L2, seed 42.
  - Vector store: Chroma 1.5.9 `PersistentClient` (`results/chroma_db`, gitignore vì dựng lại được), metric cosine, chỉ mục HNSW xấp xỉ. Tôi đối chiếu top-3 của Chroma với tìm kiếm vét cạn: trùng cả tập và thứ tự ở 22/22 câu của mỗi cấu hình (`results/ann_check.json`).
  - Lệnh chạy: `bash run_all.sh`. Môi trường: Python 3.13.18, 2 CPU, không GPU. **Chi phí API: 0 USD** (model chạy local). Chưa tính thời gian làm việc của người.
  - Lần đầu chạy, môi trường chặn `huggingface.co` nên không tải được model. Code không có fallback vector giả: nó dừng và ghi `results/errors.log`. Sau khi mở quyền truy cập mạng cho các domain của Hugging Face, ingest chạy bình thường.
- **Metadata bắt buộc, trường lọc bổ sung**
  - Metadata bắt buộc cho mỗi chunk: `document_id`, `source` (URL), `page`. Thêm `section_heading`, `heading_path`, `char_start`/`char_end`, `n_chars`, `config`, `text_sha256`, `guide_section`.
  - Trường lọc bổ sung `guide_section` ∈ {Supervised learning, Unsupervised learning, Model selection and evaluation, Dataset transformations, Inspection}. Giá trị đọc từ các file toctree của chính User Guide (`doc/supervised_learning.rst`…) bằng `src/fetch_corpus.py`, không tự đặt (`data/guide_mapping.csv`). Số trang theo mục: 117 / 63 / 58 / 45 / 5.
  - Lý do chọn: người dùng thường biết mình đang ở mục nào của User Guide, và nhiều thuật toán gần nghĩa nằm ở các mục khác nhau. Giá trị filter chỉ lấy từ câu hỏi, không lấy từ gold.

## Cấu hình và benchmark

- **A / B / C**
  - **A**: chunk cố định 500 ký tự, overlap 50, không filter.
  - **B**: chunk theo heading/đoạn (target 600, max 1.000, min 120 ký tự; khối quá dài được cắt ở ranh giới câu, rồi dòng, rồi mới cắt cứng), không filter.
  - **C**: đúng chỉ mục của B (cùng collection `day06_B`) cộng filter `guide_section` lúc truy vấn, chỉ với các câu có giá trị filter. **Khác biệt duy nhất B–C là filter**; 18 câu không có filter chạy y như B. Khác biệt A–B chỉ là cách chunk.
  - Cùng model, corpus, benchmark, metric, top-k = 3. Tham số chunk được cố định trước khi chạy, không có vòng tuning.
- **Benchmark (22 câu: 16 dev / 6 test)**
  - Câu hỏi tiếng Việt, tài liệu nguồn tiếng Anh. Loại câu: 7 trực tiếp, 5 diễn đạt lại, 6 điều kiện/ngoại lệ, 4 có filter (D14, D15 ở dev; T05, T06 ở test).
  - Kiểm chứng evidence: mỗi gold gồm trang và một câu trích (`evidence_quote`). `src/benchmark_validate.py` kiểm tra trích đoạn xuất hiện đúng một lần trong trang gold, ngưỡng quy mô (≥ 20 câu, ≥ 15 dev, ≥ 5 test, ≥ 3 câu filter trong đó ≥ 1 ở test) và giá trị filter có tồn tại trong corpus. Kết quả ở `benchmark/evidence_verification.csv`. D15 có hai trang gold hợp lệ (`tree:008`, `ensemble:001`). Dev và test chỉ dùng chung một tài liệu (`ensemble`, vì D15).
  - Đóng băng: `benchmark/FROZEN.json` lưu sha256 của `questions.json` và `selection_criteria.md` cùng thời điểm (2026-11-13T09:59:31Z); `run_experiments.py` kiểm tra lại hash trước khi chạy. Ingest hoàn tất lúc 10:31Z (A) và 10:32Z (B), truy xuất chạy lúc 10:33Z, tức đều sau mốc đóng băng. Đây là tự xác nhận bằng hash chứ không phải mốc thời gian bên ngoài; commit trên repo sẽ là mốc kiểm chứng được.
- **Tiêu chí chọn chiến lược (chốt trước khi xem test)** — `benchmark/selection_criteria.md`
  1. Evidence Hit@3 trên dev cao hơn; chênh ≤ 1 câu coi là hòa.
  2. Nếu hòa: Hit@1 trên dev (chênh ≤ 1 vẫn hòa).
  3. Nếu hòa: coherence trung bình trên cùng 10 vị trí nguồn.
  4. Nếu hòa: chiến lược rẻ hơn.
  - B so với C: C chỉ được ưu tiên khi, trên các câu filter của dev, C không tệ hơn B ở Hit@3 và top-3 của C tuân thủ filter 100%; và chỉ áp dụng khi giá trị filter được cung cấp trước truy xuất.
  - Test chỉ để báo cáo một lần. Sau khi xem kết quả test, tôi không sửa tham số chunk, benchmark hay filter.
- **Hit** = chunk trong top-k thuộc trang gold **và** chứa trọn `evidence_quote` (so khớp sau khi gộp khoảng trắng). Evidence bị cắt qua hai chunk không tính là hit. Định nghĩa này khắt khe và có lợi cho chunker không cắt giữa câu (xem phần hạn chế). Page Hit@3 (chỉ cần đúng trang) được báo cáo kèm để tách hai nguyên nhân.

## Kết quả

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| A (fixed 500/50) | dev | 7/16 | 9/16 | 2.081 | ingest 104,6 s (embed 102,5 s) | 0 USD |
| A | test | 2/6 | 3/6 | 2.081 | — | 0 USD |
| B (heading/đoạn) | dev | 10/16 | 11/16 | 1.828 | ingest 106,5 s (embed 104,4 s) | 0 USD |
| B | test | 3/6 | 5/6 | 1.828 | — | 0 USD |
| C (B + filter) | dev | 10/16 | 12/16 | 1.828 (dùng lại chỉ mục B) | 0 s ingest thêm; truy vấn TB 2,63 ms so với 2,13 ms của B | 0 USD |
| C | test | 3/6 | 5/6 | 1.828 | — | 0 USD |

Toàn bộ 22 câu: A 9/22 Hit@1 và 12/22 Evidence Hit@3; B 13/22 và 16/22; C 13/22 và 17/22. Page Hit@3 toàn bộ: A 18/22, B 19/22, C 19/22.

Thời gian đo một lần, 2 CPU, gồm cả nạp model; chênh 2 s giữa A và B nằm trong sai số đo. Độ dài chunk: A trung vị 500 ký tự, tổng 976.430 ký tự được lập chỉ mục (do overlap), tối đa 312 token. B trung vị 494 ký tự (65–999), tổng 883.681 ký tự, tối đa 455 token. Không chunk nào vượt 512 token.

Theo loại câu (Evidence Hit@3, n câu): điều kiện/ngoại lệ A 5/6, B 6/6, C 6/6; trực tiếp 5/7, 6/7, 6/7; diễn đạt lại 2/5, 3/5, 3/5; có filter 0/4, 1/4, 2/4. Bảng từng câu ở Phụ lục.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | 1,00 (n=10) | 18/18 | 0/2 (không áp filter; top-3 của T05, T06 đều lẫn chunk ngoài mục) | 0/3/3 — 1,50 |
| B | 1,80 (n=10) | 18/18 | 1/2 (không áp filter; T05 đạt, T06 không) | 0/0/6 — 2,00 |
| C | 1,80 (n=10; dùng chunk của B) | 18/18 | 2/2 (do filter) | 0/1/5 — 1,83 |

Ghi chú: metadata và filter kiểm trên top-3 của 6 câu test (18 bản ghi mỗi cấu hình). Chỉ T05 và T06 có giá trị filter nên mẫu số của cột filter là 2.

Đường dẫn và cách chọn mẫu:

- Trace top-3: `results/traces_A.jsonl`, `traces_B.jsonl`, `traces_C.jsonl`. Chỉ số: `results/metrics.csv`, `results/summary.json`.
- Coherence: 10 vị trí cố định theo quy tắc trong `src/audit.py` (sắp xếp 288 unit_id theo chữ cái, lấy chỉ số 0, k, …, 9k với k = 28, tại ký tự giữa trang), lấy chunk của A và B chứa vị trí đó. Nhãn: `results/labels/coherence_sheet_labeled.csv`. Nhãn B v0 (trước khi sửa chunker) ở `coherence_B_v0_before_fix.csv`.
- Metadata: `results/labels/metadata_check.csv` (đối chiếu tự động với corpus gốc: source, page, guide_section, offset).
- Grounding: `results/labels/grounding_sheet_labeled.csv`, thang chấm ở `results/labels/GROUNDING_RUBRIC.md` (2 = top-3 đủ ý chính; 1 = liên quan nhưng thiếu/ cắt ý chính; 0 = không đủ). Thang này được viết cùng lúc gán nhãn, sau khi đã xem top-3, nên không phải tiêu chí chốt trước.
- Nhãn coherence và grounding do Claude chấm sơ bộ (`grader = claude-llm-assisted (cần tác giả rà lại)`); cột `reviewed_by_author` đang để trống cho đến khi tôi rà lại.

## Phân tích và kết luận

- **So sánh A–B**
  - Evidence Hit@3: dev 9 → 11, test 3 → 5, toàn bộ 12 → 16. Theo cặp: B hit mà A không ở 5 câu (D01, D07, D12, T01, T05), A hit mà B không ở 1 câu (D08). Kiểm định dấu chính xác hai phía p = 0,22: hướng nhất quán nhưng chưa đủ bằng chứng thống kê với 22 câu.
  - Page Hit@3 gần như bằng nhau (A 18, B 19). Phần chênh lệch đến chủ yếu từ việc giữ nguyên vẹn evidence: với A, evidence của 4 câu (D07, D15, T01, T06) không nằm trọn trong bất kỳ chunk nào của trang gold nên chắc chắn miss theo định nghĩa Hit. Coherence tương ứng: A 1,00 so với B 1,80.
  - Vì định nghĩa Hit đòi evidence nguyên vẹn, kết quả có lợi cho B từ đầu; nó cho thấy B giữ trọn ý tốt hơn, **không** chứng minh B tìm đúng nội dung tốt hơn A về mặt ngữ nghĩa.
  - Hit@1: dev 7 → 10, test 2 → 3 (T01, T03 B hơn; T04 A hơn).
- **So sánh B–C**
  - Chỉ 4 câu có filter. Evidence Hit@3 của C hơn B đúng một câu (D15, dev; B miss, C hit). Ở test không khác (T05 cả hai hit, T06 cả hai miss). Hit@1 và Page Hit@3 không đổi ở bất kỳ câu nào.
  - Filter bảo đảm top-3 tuân thủ mục (2/2 so với 1/2 của B ở test), nhưng đó là hệ quả của cơ chế lọc, không phải bằng chứng chất lượng. Kết luận: có một câu cải thiện ở dev, chưa có bằng chứng filter giúp ở test.
  - Filter còn có thể gây hại: ở T06, filter `Inspection` loại `ensemble:006:004` (mục Supervised learning) — chunk này nêu rõ importance dựa trên impurity "favor high cardinality features", nên grounding giảm từ 2 (B) xuống 1 (C).
- **Hai ví dụ sai**
  1. **D03** (dev, diễn đạt lại; A, B, C đều miss; trang gold `preprocessing:006`). Câu hỏi: "Khi nào việc co giãn từng mẫu về chuẩn đơn vị (unit norm) là hữu ích?". Chunk chứa evidence là `B:preprocessing:006:000` (mục Normalization), hạng 12 ở B và C, hạng 26 ở A (chunk `A:preprocessing:006:000`). Top-3 của B là `kernel_approximation:000:006` (công thức ma trận), `linear_model:004:004` (danh mục tài liệu tham khảo), `decomposition:002:005` (định nghĩa chuẩn Frobenius): các chunk toàn ký hiệu toán và thuật ngữ "norm". Nguyên nhân khả dĩ: câu hỏi tiếng Việt, tài liệu tiếng Anh, model nhỏ; cụm "unit norm" khớp bề mặt với nhiều chunk "norm" khác, trong khi chunk đúng nói về "tích vô hướng/kernel". Đây là suy đoán từ các trace, tôi chưa kiểm chứng bằng thí nghiệm riêng.
  2. **D08** (dev, trực tiếp; A hit, B và C miss; trang gold `outlier_detection:003`). Cả ba cấu hình tìm đúng trang (Page Hit@3 = 1). B tách mục Isolation Forest thành ba chunk: `B:outlier_detection:003:000` (giới thiệu và định nghĩa độ dài đường đi) hạng 1, `…:002` (cài đặt) hạng 2, còn chunk chứa câu "Random partitioning produces noticeably shorter paths for anomalies" là `…:001` (328 ký tự) chỉ xếp hạng 4. Với A, cửa sổ 500 ký tự `A:outlier_detection:003:001` gom cả đoạn "đường đi trung bình là thước đo mức bình thường" và câu evidence nên xếp hạng 1. Đây là lỗi mức chunk, không phải lỗi tìm trang: chunk nhỏ ít ngữ cảnh cạnh tranh kém với chunk giới thiệu.
  - Hai trường hợp gần miss khác: **T06** (test, filter), evidence nằm ở `B:permutation_importance:001:003`, hạng 8 ở B và hạng 4 ở C, chỉ sát ngoài top-3. **D14** (dev, filter), evidence ở `linear_model:017:003`, hạng 10 ở B và hạng 4 ở C; top-3 của C là các chunk RANSAC/Theil-Sen ở `linear_model:018` và `019`. Tôi đã đọc hai trang này: chúng không chứa câu "RANSAC xử lý tốt hơn ngoại lai lớn theo hướng y", nên gold của D14 đúng và đây là lỗi truy xuất thật.
  - T06 cũng cho thấy Hit và grounding có thể lệch nhau: top-1 của B (`ensemble:006:004`, trang khác trang gold) nêu đúng ý "thiên lệch về đặc trưng nhiều giá trị" nên grounding là 2, nhưng Hit@3 vẫn tính là miss vì không phải trang gold.
- **Chiến lược chọn, đánh đổi, điều kiện áp dụng**
  - Theo tiêu chí chốt trước: B hơn A ở tiêu chí 1 (dev 11 so với 9, chênh 2 > 1). Chọn **B làm chiến lược chunk mặc định**. C chỉ dùng khi biết trước mục `guide_section` (dev: không tệ hơn B và tuân thủ filter 100%, nên thỏa điều kiện của quy tắc); bằng chứng cải thiện chỉ là một câu.
  - Đánh đổi: B ít chunk hơn 12% (1.828 so với 2.081) và ít ký tự phải nhúng hơn, nhưng độ dài chunk dao động 65–999 ký tự; chunk rất ngắn thiếu ngữ cảnh (coherence P04 `B:ensemble:012:003` chỉ khoảng 137 ký tự, và D08 ở trên). A đơn giản, kích thước đồng đều nhưng cắt giữa từ/câu (cả 10 mẫu coherence chấm 1). Filter đổi lấy độ chính xác theo mục bằng rủi ro mất bằng chứng tương đương ở mục khác (T06), và chỉ hợp lý khi người dùng cung cấp đúng giá trị.
- **Hạn chế**
  - Dữ liệu: câu hỏi tiếng Việt truy xuất tài liệu tiếng Anh bằng model nhỏ, kết quả có thể không áp dụng cho câu hỏi tiếng Anh hoặc model lớn hơn. Chuẩn hóa bằng regex làm mất hình và bảng. Mỗi câu có một (D15: hai) trang gold; bằng chứng tương đương ở trang khác không được tính là hit.
  - Test nhỏ: 6 câu test (2 câu filter), 22 câu tổng; một câu đổi chiều làm Hit@3 thay đổi 16,7 điểm phần trăm trên test và 4,5 điểm trên toàn bộ 22 câu. Không có khoảng tin cậy; kiểm định dấu cho A–B ra p = 0,22.
  - Nhãn: coherence (10 mẫu) và grounding (18 dòng) do một người chấm là LLM (Claude), cùng bên soạn benchmark và chunker, nên có nguy cơ thiên lệch, nhất là khi chấm chunk của chiến lược mình thiết kế. Nhãn B T06 = 2 là nhãn biên. Nếu đổi thành 1 thì grounding B còn 1,83, ngang C. Chưa có người chấm thứ hai nên chưa đo độ đồng thuận.
  - Độc lập của test: khi sửa chunker B v0 → v1 (v0 cắt giữa câu khi tách khối dài; sửa trước khi chạy truy xuất, sau khi xem mẫu coherence), tôi đã thấy evidence của T02 (câu test) bị tách trong v0. Vì vậy kết quả T02 của B không hoàn toàn độc lập với việc sửa này; T02 cả A, B, C đều hit nên không làm lệch so sánh. Nhãn coherence B v0 là 1,7 và v1 là 1,8.
  - Đo thời gian và chi phí: một lần chạy, 2 CPU, không lặp; chi phí 0 USD chưa tính công người; chưa đo bộ nhớ chỉ mục theo cấu hình.
  - Cách đóng băng benchmark là hash tự lưu, chưa có mốc thời gian độc lập cho tới khi commit.
- **Nếu làm lại hoặc mở rộng**
  - Thêm tìm kiếm từ khóa (BM25) kết hợp vector hoặc dịch câu hỏi sang tiếng Anh trước khi nhúng để xử lý các câu diễn đạt lại như D03, D06; thêm bộ rerank.
  - Loại hoặc gắn nhãn riêng các chunk toàn tài liệu tham khảo/công thức; thêm tiêu đề mục vào đầu văn bản chunk; gộp chunk dưới ~200 ký tự vào chunk kề (D08).
  - Mở rộng benchmark (≥ 100 câu, nhiều evidence hợp lệ cho mỗi câu), có hai người chấm độc lập và báo độ đồng thuận; báo khoảng tin cậy bằng bootstrap theo cặp; lặp lần đo thời gian; thêm câu hỏi tiếng Anh để tách ảnh hưởng của ngôn ngữ.

## Dùng AI và kiểm tra

- Công cụ: Claude (LLM) hỗ trợ viết code, soạn câu hỏi và trích đoạn evidence từ việc đọc nguồn, chấm sơ bộ nhãn coherence/grounding và soạn nháp báo cáo này.
- Kiểm tra: evidence do `benchmark_validate.py` kiểm chứng tự động; metadata đối chiếu tự động với corpus gốc; số liệu trong báo cáo đối chiếu với `results/metrics.csv`, `summary.json` và trace; top-3 của Chroma đối chiếu với tìm vét cạn (`results/ann_check.json`). Dựng lại corpus và chạy lại truy xuất cho cùng hash corpus, cùng metrics, cùng top-3 và điểm ở 66/66 cặp câu–cấu hình (`results/reproducibility_check.json`).
- Nhãn thủ công chưa được tác giả rà: cột `reviewed_by_author` còn trống. Cập nhật mục này sau khi rà: __(chưa rà)__.

## Phụ lục — kết quả từng câu (Hit@1 / Evidence Hit@3 / Page Hit@3; 1 = có)

| ID | Split | Loại | Filter | Gold | A | B | C |
|---|---|---|---|---|---|---|---|
| D01 | dev | direct | — | tree:003 | 0/0/0 | 1/1/1 | 1/1/1 |
| D02 | dev | conditional_exception | — | clustering:019 | 1/1/1 | 1/1/1 | 1/1/1 |
| D03 | dev | paraphrase | — | preprocessing:006 | 0/0/0 | 0/0/0 | 0/0/0 |
| D04 | dev | conditional_exception | — | cross_validation:007 | 1/1/1 | 1/1/1 | 1/1/1 |
| D05 | dev | direct | — | svm:003 | 0/1/1 | 0/1/1 | 0/1/1 |
| D06 | dev | paraphrase | — | naive_bayes:002 | 0/0/0 | 0/0/0 | 0/0/0 |
| D07 | dev | direct | — | model_evaluation:007 | 0/0/1 | 1/1/1 | 1/1/1 |
| D08 | dev | direct | — | outlier_detection:003 | 1/1/1 | 0/0/1 | 0/0/1 |
| D09 | dev | conditional_exception | — | linear_model:005 | 1/1/1 | 1/1/1 | 1/1/1 |
| D10 | dev | conditional_exception | — | grid_search:006 | 0/1/1 | 1/1/1 | 1/1/1 |
| D11 | dev | direct | — | impute:004 | 1/1/1 | 1/1/1 | 1/1/1 |
| D12 | dev | paraphrase | — | calibration:002 | 0/0/1 | 1/1/1 | 1/1/1 |
| D13 | dev | direct | — | clustering:001 | 1/1/1 | 1/1/1 | 1/1/1 |
| D14 | dev | filter | Supervised learning | linear_model:017 | 0/0/1 | 0/0/0 | 0/0/0 |
| D15 | dev | filter | Supervised learning | tree:008, ensemble:001 | 0/0/0 | 0/0/1 | 0/1/1 |
| D16 | dev | paraphrase | — | lda_qda:003 | 1/1/1 | 1/1/1 | 1/1/1 |
| T01 | test | conditional_exception | — | decomposition:001 | 0/0/1 | 1/1/1 | 1/1/1 |
| T02 | test | conditional_exception | — | ensemble:005 | 1/1/1 | 1/1/1 | 1/1/1 |
| T03 | test | paraphrase | — | neighbors:008 | 0/1/1 | 1/1/1 | 1/1/1 |
| T04 | test | direct | — | random_projection:001 | 1/1/1 | 0/1/1 | 0/1/1 |
| T05 | test | filter | Unsupervised learning | density:001 | 0/0/1 | 0/1/1 | 0/1/1 |
| T06 | test | filter | Inspection | permutation_importance:001 | 0/0/1 | 0/0/1 | 0/0/1 |

C dùng cùng chỉ mục với B; cột C chỉ khác B ở các câu có filter (D14, D15, T05, T06).

