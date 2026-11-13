"""Phân tích lỗi (chỉ đọc, không đổi kết quả đã đóng băng): với mỗi (cấu hình, câu) KHÔNG đạt Evidence Hit@3,
tìm hạng (trong top-50) của chunk đầu tiên chứa trọn evidence ở trang gold, và hạng của chunk đầu tiên thuộc trang gold.
Cũng kiểm tra evidence có nằm trọn trong BẤT KỲ chunk nào của trang gold không (nếu không: evidence bị cắt đôi).

Chạy: python3 -I src/error_analysis.py  ->  results/error_analysis.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunking import norm_ws  # noqa: E402
from ingest import DEFAULT_MODEL, Embedder, get_client, get_collection  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = {"A": ("day06_A", False), "B": ("day06_B", False), "C": ("day06_B", True)}
DEPTH = 50


def main():
    qs = json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))["questions"]
    traces = {c: {t["question_id"]: t for t in map(json.loads, open(ROOT / "results" / f"traces_{c}.jsonl", encoding="utf-8"))} for c in CONFIGS}
    chunks = {c: [json.loads(l) for l in open(ROOT / "results" / f"chunks_{c}.jsonl", encoding="utf-8")] for c in "AB"}
    emb = Embedder(DEFAULT_MODEL)
    client = get_client()
    cols = {n: get_collection(client, n) for n in {v[0] for v in CONFIGS.values()}}
    qvec = {q["id"]: v for q, v in zip(qs, emb.queries([q["question"] for q in qs]))}
    out = []
    for q in qs:
        for cfg, (cname, use_filter) in CONFIGS.items():
            if traces[cfg][q["id"]]["evidence_hit_at_3"]:
                continue
            flt = q.get("filter") if use_filter else None
            where = {flt["field"]: flt["value"]} if flt else None
            res = cols[cname].query(query_embeddings=[qvec[q["id"]].tolist()], n_results=DEPTH, where=where,
                                    include=["documents", "metadatas", "distances"])
            gold = {g["gold_page"]: norm_ws(g["evidence_quote"]) for g in q["gold"]}
            rank_ev = rank_page = None
            for i, (cid, doc, md) in enumerate(zip(res["ids"][0], res["documents"][0], res["metadatas"][0]), 1):
                if md["page"] in gold:
                    rank_page = rank_page or i
                    if gold[md["page"]] in norm_ws(doc):
                        rank_ev = i
                        break
            base = "A" if cfg == "A" else "B"
            contained_any = {p: [c["chunk_id"] for c in chunks[base] if c["unit_id"] == p and ev in norm_ws(c["text"])] for p, ev in gold.items()}
            out.append({
                "config": cfg, "question_id": q["id"], "split": q["split"], "type": q["type"],
                "gold_pages": list(gold), "top3": [r["chunk_id"] for r in traces[cfg][q["id"]]["top3"]],
                "rank_first_gold_page_chunk": rank_page, "rank_first_evidence_chunk": rank_ev,
                "evidence_fully_inside_some_chunk": {p: bool(v) for p, v in contained_any.items()},
                "evidence_chunk_ids": contained_any,
                "searched_depth": DEPTH,
            })
    (ROOT / "results" / "error_analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for r in out:
        print(r["config"], r["question_id"], "page_rank", r["rank_first_gold_page_chunk"], "evidence_rank", r["rank_first_evidence_chunk"],
              "contained:", r["evidence_fully_inside_some_chunk"], r["evidence_chunk_ids"])


if __name__ == "__main__":
    main()
