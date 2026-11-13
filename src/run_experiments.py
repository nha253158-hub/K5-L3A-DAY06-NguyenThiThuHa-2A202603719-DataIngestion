"""Chạy 3 cấu hình trên cùng bộ câu hỏi đã đóng băng; lưu trace top-3 và tính Hit@1 / Evidence Hit@3.

  A: collection day06_A, không filter
  B: collection day06_B, không filter
  C: collection day06_B (cùng chỉ mục với B), filter guide_section CHỈ cho câu có filter
     (câu không có filter chạy y như B và được ghi rõ).

Chạy: python3 -I src/run_experiments.py
"""
import csv
import hashlib
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunking import norm_ws  # noqa: E402
from ingest import DEFAULT_MODEL, Embedder, get_client, get_collection, log_error  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TOPK = 3
CONFIGS = {"A": ("day06_A", False), "B": ("day06_B", False), "C": ("day06_B", True)}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_frozen():
    fz = json.loads((ROOT / "benchmark" / "FROZEN.json").read_text(encoding="utf-8"))
    cur = {"questions": sha(ROOT / "benchmark" / "questions.json"),
           "criteria": sha(ROOT / "benchmark" / "selection_criteria.md")}
    if cur["questions"] != fz["questions_sha256"] or cur["criteria"] != fz["selection_criteria_sha256"]:
        raise SystemExit("Benchmark/tiêu chí đã bị sửa sau khi đóng băng. Ghi rõ lý do và đóng băng lại bằng "
                         "src/benchmark_validate.py rồi chạy lại (kết quả cũ không còn là kiểm tra độc lập).")
    return fz


def evaluate(q, rows):
    gold = q["gold"]
    gold_pages = {g["gold_page"] for g in gold}
    flags = []
    for r in rows:
        page_ok = r["metadata"]["page"] in gold_pages
        doc = norm_ws(r["text"])
        ev_ok = page_ok and any(norm_ws(g["evidence_quote"]) in doc for g in gold if g["gold_page"] == r["metadata"]["page"])
        flags.append({"page_ok": page_ok, "evidence_ok": ev_ok})
    return flags


def main():
    fz = check_frozen()
    qs = json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))["questions"]
    try:
        emb = Embedder(DEFAULT_MODEL)
    except RuntimeError as e:
        print("LỖI:", e, file=sys.stderr)
        sys.exit(2)
    client = get_client()
    cols = {name: get_collection(client, name) for name in {v[0] for v in CONFIGS.values()}}
    for name, col in cols.items():
        if col.count() == 0:
            raise SystemExit(f"Collection {name} rỗng: chạy src/ingest.py trước.")
    t0 = time.perf_counter()
    qvecs = emb.queries([q["question"] for q in qs])  # nhúng câu hỏi MỘT lần, dùng chung cho cả 3 cấu hình
    t_qembed = time.perf_counter() - t0
    traces, summary_rows, latency = {c: [] for c in CONFIGS}, [], {}
    for cfg, (cname, use_filter) in CONFIGS.items():
        lat = []
        for q, vec in zip(qs, qvecs):
            flt = q.get("filter") if use_filter else None
            where = {flt["field"]: flt["value"]} if flt else None
            t1 = time.perf_counter()
            res = cols[cname].query(query_embeddings=[vec.tolist()], n_results=TOPK, where=where,
                                    include=["documents", "metadatas", "distances"])
            lat.append((time.perf_counter() - t1) * 1000)
            rows = [{"rank": i + 1, "chunk_id": res["ids"][0][i], "score_cosine": round(1 - res["distances"][0][i], 5),
                     "text": res["documents"][0][i], "metadata": res["metadatas"][0][i]} for i in range(len(res["ids"][0]))]
            flags = evaluate(q, rows)
            for r, f in zip(rows, flags):
                r.update(f)
            traces[cfg].append({
                "config": cfg, "question_id": q["id"], "split": q["split"], "type": q["type"], "question": q["question"],
                "filter_in_question": q.get("filter"), "filter_applied": bool(flt),
                "gold_pages": [g["gold_page"] for g in q["gold"]], "top3": rows,
                "hit_at_1": flags[0]["evidence_ok"] if flags else False,
                "evidence_hit_at_3": any(f["evidence_ok"] for f in flags),
                "page_hit_at_3": any(f["page_ok"] for f in flags),
                "filter_compliant_top3": (all(r["metadata"]["guide_section"] == flt["value"] for r in rows) if flt else None),
            })
        latency[cfg] = round(sum(lat) / len(lat), 2)
        with open(ROOT / "results" / f"traces_{cfg}.jsonl", "w", encoding="utf-8") as f:
            for t in traces[cfg]:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    # chỉ số theo split (và theo nhóm câu filter)
    with open(ROOT / "results" / "metrics.csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["config", "subset", "n_questions", "hit_at_1", "evidence_hit_at_3", "page_hit_at_3", "filter_compliant", "n_filter_questions"])
        for cfg, tr in traces.items():
            subsets = {"dev": lambda t: t["split"] == "dev", "test": lambda t: t["split"] == "test",
                       "all": lambda t: True, "dev_filter_questions": lambda t: t["split"] == "dev" and t["filter_in_question"],
                       "test_filter_questions": lambda t: t["split"] == "test" and t["filter_in_question"]}
            for name, pred in subsets.items():
                sub = [t for t in tr if pred(t)]
                fq = [t for t in sub if t["filter_in_question"]]
                comp = [t["filter_compliant_top3"] for t in fq if t["filter_applied"]]
                w.writerow([cfg, name, len(sub), sum(t["hit_at_1"] for t in sub), sum(t["evidence_hit_at_3"] for t in sub),
                            sum(t["page_hit_at_3"] for t in sub), f"{sum(comp)}/{len(comp)}" if comp else "N/A", len(fq)])
    import chromadb
    meta = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": emb.name, "model_revision": emb.revision,
        "versions": {**emb.versions, "chromadb": chromadb.__version__}, "top_k": TOPK, "benchmark_frozen": fz,
        "seconds_query_embedding_all_questions": round(t_qembed, 3), "mean_query_latency_ms": latency,
        "cost_usd": 0.0, "platform": platform.platform(),
    }
    (ROOT / "results" / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(open(ROOT / "results" / "metrics.csv", encoding="utf-8").read())


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        log_error(f"run_experiments lỗi: {e!r}")
        raise
