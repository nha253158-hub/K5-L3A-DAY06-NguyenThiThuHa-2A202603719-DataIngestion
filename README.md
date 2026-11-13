# Day 06 — Data Ingestion Engineering (bài cá nhân)

Biến tài liệu mở thành knowledge base truy xuất được, rồi đo chiến lược chuẩn bị dữ liệu nào hiệu quả hơn.

- **Corpus**: scikit-learn 1.9.1 User Guide (`doc/modules/*.rst`), giấy phép BSD-3-Clause. 40 tài liệu, **288 trang nội dung** (mỗi trang ≥ 1.500 ký tự chuẩn hóa), ~887 nghìn ký tự.
- **Embedding**: `intfloat/multilingual-e5-small` (local, 384 chiều, prefix `query:` / `passage:`, vector chuẩn hóa L2). Chi phí API = 0.
- **Vector store**: Chroma 1.5.9 `PersistentClient`, metric cosine (HNSW, tìm kiếm xấp xỉ), có metadata filter.
- **Ba cấu hình**: A = chunk cố định 500/50, không filter · B = chunk theo heading/đoạn (target 600, max 1000), không filter · C = B + filter `guide_section` (chỉ cho câu có filter; dùng lại chỉ mục của B nên B–C chỉ khác nhau ở filter).
- **Benchmark**: 22 câu (16 dev / 6 test), 4 câu có filter (2 dev, 2 test), đóng băng bằng hash trước khi chạy truy xuất.

## Trạng thái

- [x] Corpus, manifest, chuẩn hóa, log lỗi chuẩn hóa
- [x] Benchmark + kiểm chứng evidence + đóng băng (`benchmark/FROZEN.json`) + tiêu chí chọn chiến lược chốt trước
- [x] Hai chunker, thống kê chunk, nhãn coherence (10 vị trí cố định theo quy tắc)
- [x] Ingest (embed + lưu Chroma, nạp lại không nhân đôi), chạy 3 cấu hình, trace top-3, Hit@1 / Evidence Hit@3
- [x] Kiểm tra metadata, grounding, phân tích lỗi, báo cáo cá nhân
- [ ] Tác giả rà lại các nhãn do LLM chấm sơ bộ (`results/labels/*_labeled.csv`, cột `reviewed_by_author`) và điền commit chốt bài vào `STUDENT.md`

## Kết quả chính (22 câu; Hit@1 / Evidence Hit@3)

| Cấu hình | Dev (16) | Test (6) | Chunk | Coherence /2 | Grounding /2 (test) |
|---|---|---|---|---|---|
| A — fixed 500/50 | 7 / 9 | 2 / 3 | 2.081 | 1,00 | 1,50 |
| B — heading/đoạn | 10 / 11 | 3 / 5 | 1.828 | 1,80 | 2,00 |
| C — B + filter | 10 / 12 | 3 / 5 | 1.828 | 1,80 | 1,83 |

B hơn A ở 5 câu, kém A ở 1 câu (kiểm định dấu p = 0,22); C hơn B đúng 1 câu (D15). Mẫu nhỏ nên chỉ mang tính minh họa. Phân tích đầy đủ, hạn chế và ví dụ sai: `report/individual/2A202603719_NguyenThiThuHa.md`.

## Cấu trúc

```text
STUDENT.md
README.md
run_all.sh                    # chạy lại toàn bộ
requirements.txt
src/
  fetch_corpus.py             # tải docs ở tag 1.9.1, ghi data/fetch_log.csv, data/guide_mapping.csv
  build_corpus.py             # chuẩn hóa RST -> văn bản, tách trang, ghi manifest + normalization_log
  chunking.py                 # chunker A (fixed) và B (heading/đoạn)
  ingest.py                   # embed + lưu Chroma, nạp lại không nhân đôi, thống kê chunk
  run_experiments.py          # chạy A/B/C, trace top-3, metrics
  benchmark_validate.py       # kiểm chứng evidence + đóng băng benchmark
  audit.py                    # mẫu coherence, kiểm tra metadata, bảng grounding, tổng hợp
  error_analysis.py           # hạng của chunk đúng với các câu miss -> results/error_analysis.json
  ann_check.py                # đối chiếu top-3 của Chroma (HNSW) với tìm vét cạn -> results/ann_check.json
  summarize_results.py        # bảng số liệu, so sánh cặp A-B / B-C -> results/summary.json
data/
  raw/                        # file RST gốc (BSD-3, kèm COPYING)
  corpus/units.jsonl          # 288 trang đã chuẩn hóa
  manifest.csv                # nguồn, quyền, thời điểm truy cập, page ID, số ký tự
  fetch_log.csv  guide_mapping.csv
benchmark/
  questions.json              # câu hỏi, đáp án, gold, evidence, filter, split
  evidence_verification.csv   # kết quả kiểm chứng evidence
  selection_criteria.md       # tiêu chí chọn chiến lược (chốt trước khi chạy)
  FROZEN.json                 # hash + thời điểm đóng băng
artifacts/experiment_log.csv  # giả thuyết A/B/C viết trước khi chạy
results/
  normalization_log.csv  corpus_stats.json
  labels/                     # nhãn coherence, bảng metadata, bảng grounding
  traces_{A,B,C}.jsonl  metrics.csv  ingest_stats_{A,B}.json  run_meta.json
  chunks_{A,B}.jsonl  aspects_summary.json  summary.json  error_analysis.json  ann_check.json
  chroma_db/                  # chỉ mục vector, gitignore, dựng lại bằng src/ingest.py
report/individual/2A202603719_NguyenThiThuHa.md
```

## Chạy lại

```bash
bash run_all.sh
```

Hoặc từng bước: xem `run_all.sh`. Cần Python ≥ 3.11 và mạng tới `raw.githubusercontent.com` (tải docs) và `huggingface.co` (tải model lần đầu). Máy 2 CPU, không GPU là đủ.

## Quyết định thiết kế chính

- **Trang (page)**: tài liệu RST không có phân trang, nên một trang = một đơn vị liên tục bắt đầu ở tiêu đề mục cấp ≤ 3, ≥ 1.500 ký tự chuẩn hóa; mục ngắn hơn được gộp vào đơn vị trước, không bỏ nội dung. Hai tài liệu quá ngắn (`isotonic`, `unsupervised_reduction`) bị loại và được ghi trong `results/corpus_stats.json`.
- **Trường lọc**: `guide_section` ∈ {Supervised learning, Unsupervised learning, Model selection and evaluation, Dataset transformations, Inspection}. Giá trị đọc từ các file toctree của chính User Guide (`doc/supervised_learning.rst`, …), không tự đặt.
- **Hit**: chunk thuộc đúng trang gold và chứa đủ `evidence_quote` (so khớp sau khi gộp khoảng trắng). Evidence bị tách qua hai chunk thì không tính hit.
- **Nạp lại không nhân đôi**: `chunk_id` xác định + `text_sha256`; chunk không đổi bị bỏ qua, chunk đổi được upsert, chunk không còn tồn tại bị xóa. `--idempotency-check` ghi kết quả vào `ingest_stats_*.json`.

## Dùng AI và rủi ro thiên lệch

Claude (LLM) hỗ trợ viết code, soạn câu hỏi/evidence từ việc đọc nguồn, chấm sơ bộ các nhãn coherence/grounding và soạn nháp báo cáo. Evidence được script kiểm chứng tự động; mọi nhãn ghi rõ `grader = claude-llm-assisted` kèm lý do và cột `reviewed_by_author` để tác giả rà lại. Người soạn benchmark, người viết chunker và người chấm là cùng một bên nên có nguy cơ thiên lệch (ví dụ chấm chunk của chiến lược mình thiết kế); tập test chỉ 6 câu nên kết quả chỉ mang tính minh họa.

## Giới hạn đã biết

- Chuẩn hóa RST bằng regex, không dùng Sphinx: hình/figure bị bỏ (câu như "Here is an example…" mất hình), bảng grid chỉ còn văn bản thô, còn 9 chuỗi `**` và 4 dấu backtick lạc (do lỗi nguồn hoặc giới hạn của regex); số liệu từng tài liệu trong `results/normalization_log.csv`.
- Chunker B có hai phiên bản: v0 cắt giữa câu khi tách khối dài (phát hiện khi xem mẫu coherence trước khi chạy truy xuất, nhãn v0 lưu ở `results/labels/coherence_B_v0_before_fix.csv`); v1 chỉ cắt ở ranh giới câu, dòng, rồi mới cắt cứng. Lúc sửa, tác giả đã thấy rằng evidence của T02 (câu test) bị tách trong B v0, nên kết quả T02 của B không hoàn toàn độc lập với việc sửa này.
