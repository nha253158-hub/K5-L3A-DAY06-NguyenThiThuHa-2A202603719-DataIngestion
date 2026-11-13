"""Kiểm chứng benchmark TRƯỚC khi chạy thí nghiệm, rồi "đóng băng" bằng hash + thời điểm.

Kiểm tra:
  * mỗi evidence_quote nằm trong đúng trang gold (so khớp sau khi gộp khoảng trắng),
  * evidence xuất hiện đúng 1 lần trong trang gold, và liệt kê các trang khác có chứa nó,
  * quy mô: >=20 câu, >=15 dev, >=5 test, >=3 câu filter (>=1 ở test),
  * dev và test không dùng chung tài liệu gold (báo cáo ngoại lệ nếu có),
  * giá trị filter tồn tại trong metadata corpus.

Chạy: python3 -I src/benchmark_validate.py
"""
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QPATH = ROOT / "benchmark" / "questions.json"


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def main():
    units = {}
    for line in open(ROOT / "data" / "corpus" / "units.jsonl", encoding="utf-8"):
        u = json.loads(line)
        units[u["unit_id"]] = u
    sections = {u["guide_section"] for u in units.values()}
    data = json.loads(QPATH.read_text(encoding="utf-8"))
    qs = data["questions"]
    errors, rows = [], []
    for q in qs:
        for g in q["gold"]:
            uid, ev = g["gold_page"], norm_ws(g["evidence_quote"])
            u = units.get(uid)
            if u is None:
                errors.append(f"{q['id']}: không có trang {uid}")
                continue
            if u["doc_id"] != g["gold_source_id"]:
                errors.append(f"{q['id']}: gold_source_id {g['gold_source_id']} != doc_id {u['doc_id']}")
            text = norm_ws(u["text"])
            n = text.count(ev)
            others = [k for k, v in units.items() if k != uid and ev in norm_ws(v["text"])]
            if n != 1:
                errors.append(f"{q['id']}: evidence xuất hiện {n} lần trong {uid}")
            rows.append({"question_id": q["id"], "split": q["split"], "gold_page": uid, "occurrences_in_gold_page": n,
                         "also_found_in_other_pages": ";".join(others), "evidence_chars": len(ev),
                         "guide_section_of_gold": u["guide_section"]})
        f = q.get("filter")
        if f and f["value"] not in sections:
            errors.append(f"{q['id']}: filter value {f['value']} không tồn tại trong corpus")
    dev = [q for q in qs if q["split"] == "dev"]
    test = [q for q in qs if q["split"] == "test"]
    filt = [q for q in qs if q.get("filter")]
    if len(qs) < 20 or len(dev) < 15 or len(test) < 5:
        errors.append(f"quy mô chưa đủ: total={len(qs)} dev={len(dev)} test={len(test)}")
    if len(filt) < 3 or not any(q["split"] == "test" for q in filt):
        errors.append("cần >=3 câu filter, trong đó >=1 ở test")
    docs = lambda L: {g["gold_source_id"] for q in L for g in q["gold"]}
    overlap = sorted(docs(dev) & docs(test))
    with open(ROOT / "benchmark" / "evidence_verification.csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summary = {
        "total": len(qs), "dev": len(dev), "test": len(test), "filter_questions": len(filt),
        "filter_in_test": sum(1 for q in filt if q["split"] == "test"),
        "types": {t: sum(1 for q in qs if q["type"] == t) for t in sorted({q["type"] for q in qs})},
        "dev_test_shared_gold_docs": overlap, "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        sys.exit(1)
    crit = ROOT / "benchmark" / "selection_criteria.md"
    fpath = ROOT / "benchmark" / "FROZEN.json"
    if fpath.exists():  # đã đóng băng: chỉ xác nhận, KHÔNG ghi đè mốc thời gian
        old = json.loads(fpath.read_text(encoding="utf-8"))
        same = old["questions_sha256"] == hashlib.sha256(QPATH.read_bytes()).hexdigest() and \
            old.get("selection_criteria_sha256") == (hashlib.sha256(crit.read_bytes()).hexdigest() if crit.exists() else None)
        if same:
            print(f"OK - benchmark khớp mốc đóng băng cũ ({old['frozen_at_utc']}), giữ nguyên.")
            return
        if "--refreeze" not in sys.argv:
            print("Benchmark/tiêu chí khác với bản đã đóng băng. Nếu sửa có chủ đích, chạy lại với --refreeze và ghi rõ "
                  "trong báo cáo (kết quả cũ không còn là kiểm tra độc lập).")
            sys.exit(3)
    frozen = {
        "questions_sha256": hashlib.sha256(QPATH.read_bytes()).hexdigest(),
        "selection_criteria_sha256": hashlib.sha256(crit.read_bytes()).hexdigest() if crit.exists() else None,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Hash này được run_experiments.py kiểm tra lại; sửa questions.json sau thời điểm này phải được ghi rõ.",
        **{k: v for k, v in summary.items() if k != "errors"},
    }
    (ROOT / "benchmark" / "FROZEN.json").write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK - đã đóng băng benchmark")


if __name__ == "__main__":
    main()
