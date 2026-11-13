#!/usr/bin/env bash
# Chạy lại toàn bộ pipeline từ đầu (cần mạng tới raw.githubusercontent.com và huggingface.co).
# Dùng: bash run_all.sh        (Python >= 3.11)
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install -r requirements.txt

python3 -I src/fetch_corpus.py                      # tải docs scikit-learn 1.9.1 + log truy cập
python3 -I src/build_corpus.py                      # chuẩn hóa RST, tách 288 trang, manifest
python3 -I src/benchmark_validate.py                # kiểm chứng evidence; giữ nguyên mốc đóng băng nếu đã có
python3 -I src/ingest.py --config A --config B --idempotency-check   # chunk + embed + lưu Chroma
python3 -I src/run_experiments.py                   # 3 cấu hình, top-3, Hit@1 / Evidence Hit@3
python3 -I src/audit.py metadata-check              # đối chiếu metadata top-3 của câu test
python3 -I src/audit.py grounding-sheet             # bảng top-3 để chấm grounding (ghi grounding_sheet.csv chưa có nhãn)
python3 -I src/audit.py summarize                   # tổng hợp từ các file *_labeled.csv đã có trong results/labels/
python3 -I src/error_analysis.py                    # hạng của chunk đúng với các câu miss
python3 -I src/ann_check.py                         # đối chiếu HNSW với tìm vét cạn
python3 -I src/summarize_results.py                 # bảng số liệu và so sánh cặp
echo "Xong. Nhãn thủ công nằm ở results/labels/ (coherence_sheet_labeled.csv, grounding_sheet_labeled.csv)."
