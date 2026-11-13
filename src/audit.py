"""Công cụ cho phần đánh giá thủ công / bán thủ công (5 khía cạnh).

Lệnh:
  coherence-sample   chọn 10 vị trí nguồn CỐ ĐỊNH theo quy tắc (trước khi xem bất kỳ điểm nào) và xuất các chunk
                     của A và B chứa vị trí đó -> results/labels/coherence_sheet.csv
  metadata-check     đối chiếu source/page/guide_section/offset của top-3 (câu test) với corpus gốc
                     -> results/labels/metadata_check.csv  (kiểm tra tự động, dùng để hỗ trợ người chấm)
  grounding-sheet    xuất top-3 của các câu test cho mỗi cấu hình -> results/labels/grounding_sheet.csv
  summarize          đọc các file nhãn đã điền -> results/aspects_summary.json

Quy tắc chọn vị trí coherence (cố định trước khi chấm):
  sắp xếp tất cả unit_id theo thứ tự chữ cái; lấy unit ở chỉ số 0, k, 2k, ..., 9k với k = N // 10;
  vị trí = ký tự giữa trang (char_count // 2). Với mỗi chiến lược lấy chunk chứa vị trí đó
  (nếu có hai chunk chồng lấn, lấy chunk bắt đầu sớm hơn; nếu vị trí rơi vào khoảng trắng giữa hai chunk, lấy chunk liền sau).
"""
import csv
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunking import make_chunks, norm_ws  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "results" / "labels"


def load_units():
    return {u["unit_id"]: u for u in (json.loads(l) for l in open(ROOT / "data" / "corpus" / "units.jsonl", encoding="utf-8"))}


def coherence_sample():
    units = load_units()
    ids = sorted(units)
    k = len(ids) // 10
    picks = [ids[i * k] for i in range(10)]
    LAB.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, uid in enumerate(picks, 1):
        u = units[uid]
        pos = u["char_count"] // 2
        for cfg in ("A", "B"):
            chunks = make_chunks(u, cfg)
            cover = [c for c in chunks if c.char_start <= pos < c.char_end]
            if not cover:  # vị trí rơi vào khoảng trắng giữa hai chunk (B bỏ khoảng trắng phân cách): lấy chunk liền sau
                cover = [c for c in chunks if c.char_start >= pos][:1] or chunks[-1:]
            c = sorted(cover, key=lambda x: x.char_start)[0]
            rows.append({"position_id": f"P{n:02d}", "unit_id": uid, "offset": pos, "strategy": cfg, "chunk_id": c.chunk_id,
                         "char_start": c.char_start, "char_end": c.char_end, "chunk_text": c.text,
                         "label_0_1_2": "", "reason": "", "grader": "", "reviewed_by_author": ""})
    path = LAB / "coherence_sheet.csv"
    with open(path, "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("positions:", picks)
    print("wrote", path)


def read_traces(cfg):
    return [json.loads(l) for l in open(ROOT / "results" / f"traces_{cfg}.jsonl", encoding="utf-8")]


def metadata_check():
    units = load_units()
    manifest = {r["source_id"]: r for r in csv.DictReader(open(ROOT / "data" / "manifest.csv", encoding="utf-8"))}
    rows = []
    for cfg in ("A", "B", "C"):
        for t in read_traces(cfg):
            if t["split"] != "test":
                continue
            for r in t["top3"]:
                m = r["metadata"]
                u = units.get(m["page"])
                errs = []
                if u is None:
                    errs.append("page không tồn tại")
                else:
                    if m["document_id"] != u["doc_id"]:
                        errs.append("document_id sai")
                    if m["source"] != u["source"]:
                        errs.append("source không khớp URL nguồn")
                    if m["guide_section"] != u["guide_section"]:
                        errs.append("guide_section sai")
                    if u["text"][m["char_start"]:m["char_end"]] != r["text"]:
                        errs.append("offset không khớp văn bản gốc")
                    if manifest.get(m["document_id"], {}).get("guide_section") != m["guide_section"]:
                        errs.append("guide_section lệch manifest")
                rows.append({"config": cfg, "question_id": t["question_id"], "rank": r["rank"], "chunk_id": r["chunk_id"],
                             "document_id": m["document_id"], "page": m["page"], "guide_section": m["guide_section"],
                             "source": m["source"], "complete_and_correct": not errs, "errors": "; ".join(errs),
                             "filter_required": bool(t["filter_in_question"]),
                             "filter_ok": (m["guide_section"] == t["filter_in_question"]["value"]) if t["filter_in_question"] else ""})
    LAB.mkdir(parents=True, exist_ok=True)
    with open(LAB / "metadata_check.csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("records:", len(rows), "ok:", sum(r["complete_and_correct"] for r in rows))


def grounding_sheet():
    qs = {q["id"]: q for q in json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))["questions"]}
    rows = []
    for cfg in ("A", "B", "C"):
        for t in read_traces(cfg):
            if t["split"] != "test":
                continue
            q = qs[t["question_id"]]
            rows.append({"config": cfg, "question_id": t["question_id"], "question": q["question"],
                         "expected_answer": q["expected_answer"], "gold_pages": ";".join(t["gold_pages"]),
                         "top1_chunk": t["top3"][0]["chunk_id"] if t["top3"] else "",
                         "top3_chunk_ids": " | ".join(r["chunk_id"] for r in t["top3"]),
                         "top3_texts": "\n=====\n".join(f"[{r['rank']}] {r['chunk_id']} (score {r['score_cosine']})\n{r['text']}" for r in t["top3"]),
                         "label_0_1_2": "", "reason": "", "grader": "", "reviewed_by_author": ""})
    LAB.mkdir(parents=True, exist_ok=True)
    with open(LAB / "grounding_sheet.csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("wrote", len(rows), "rows")


def mean_counts(vals):
    vals = [int(v) for v in vals]
    return {"n": len(vals), "counts": {str(k): vals.count(k) for k in (0, 1, 2)}, "mean_of_2": round(st.mean(vals), 3) if vals else None}


def summarize():
    out = {}
    coh = list(csv.DictReader(open(LAB / "coherence_sheet_labeled.csv", encoding="utf-8")))
    out["coherence"] = {s: mean_counts([r["label_0_1_2"] for r in coh if r["strategy"] == s]) for s in ("A", "B")}
    out["coherence"]["C"] = out["coherence"]["B"]  # C dùng chunk của B
    gr = list(csv.DictReader(open(LAB / "grounding_sheet_labeled.csv", encoding="utf-8")))
    out["grounding"] = {c: mean_counts([r["label_0_1_2"] for r in gr if r["config"] == c]) for c in ("A", "B", "C")}
    md = list(csv.DictReader(open(LAB / "metadata_check.csv", encoding="utf-8")))
    out["metadata"] = {}
    for c in ("A", "B", "C"):
        sub = [r for r in md if r["config"] == c]
        fq = {r["question_id"] for r in sub if r["filter_required"] == "True"}
        ok_fq = {q for q in fq if all(r["filter_ok"] == "True" for r in sub if r["question_id"] == q)}
        out["metadata"][c] = {"complete_and_correct": f"{sum(r['complete_and_correct'] == 'True' for r in sub)}/{len(sub)}",
                              "filter_compliant_questions": f"{len(ok_fq)}/{len(fq)}" if fq else "N/A"}
    (ROOT / "results" / "aspects_summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    {"coherence-sample": coherence_sample, "metadata-check": metadata_check,
     "grounding-sheet": grounding_sheet, "summarize": summarize}[sys.argv[1]]()
