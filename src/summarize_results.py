"""Tổng hợp số liệu cho báo cáo từ traces/ingest stats/nhãn (không chạy lại truy xuất).

Chạy: python3 -I src/summarize_results.py  ->  results/summary.json  (và in bảng)
Gồm: Hit@1 / Evidence Hit@3 / Page Hit@3 theo split và theo loại câu, so sánh cặp A-B và B-C (đếm câu chênh lệch,
kiểm định dấu hai phía chính xác), thống kê chunk, thời gian/chi phí, kết quả 5 khía cạnh.
"""
import json
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sign_test_two_sided(b_only: int, a_only: int) -> float:
    n = b_only + a_only
    if n == 0:
        return 1.0
    k = min(b_only, a_only)
    p = sum(comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def main():
    qs = {q["id"]: q for q in json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))["questions"]}
    tr = {c: {t["question_id"]: t for t in map(json.loads, open(ROOT / "results" / f"traces_{c}.jsonl", encoding="utf-8"))} for c in "ABC"}
    out = {"per_config": {}, "by_type": {}, "paired": {}}
    for c in "ABC":
        out["per_config"][c] = {}
        for name, pred in {"dev": lambda q: q["split"] == "dev", "test": lambda q: q["split"] == "test", "all": lambda q: True}.items():
            ids = [i for i, q in qs.items() if pred(q)]
            out["per_config"][c][name] = {
                "n": len(ids), "hit_at_1": sum(tr[c][i]["hit_at_1"] for i in ids),
                "evidence_hit_at_3": sum(tr[c][i]["evidence_hit_at_3"] for i in ids),
                "page_hit_at_3": sum(tr[c][i]["page_hit_at_3"] for i in ids)}
        out["by_type"][c] = {}
        for ty in sorted({q["type"] for q in qs.values()}):
            ids = [i for i, q in qs.items() if q["type"] == ty]
            out["by_type"][c][ty] = {"n": len(ids), "hit_at_1": sum(tr[c][i]["hit_at_1"] for i in ids),
                                     "evidence_hit_at_3": sum(tr[c][i]["evidence_hit_at_3"] for i in ids),
                                     "page_hit_at_3": sum(tr[c][i]["page_hit_at_3"] for i in ids)}
    for x, y in (("A", "B"), ("B", "C")):
        for metric in ("evidence_hit_at_3", "hit_at_1", "page_hit_at_3"):
            for name, pred in {"dev": lambda q: q["split"] == "dev", "test": lambda q: q["split"] == "test", "all": lambda q: True}.items():
                ids = [i for i, q in qs.items() if pred(q)]
                y_only = [i for i in ids if tr[y][i][metric] and not tr[x][i][metric]]
                x_only = [i for i in ids if tr[x][i][metric] and not tr[y][i][metric]]
                out["paired"][f"{x}->{y}|{metric}|{name}"] = {
                    f"{y}_only": y_only, f"{x}_only": x_only, "sign_test_p_two_sided": round(sign_test_two_sided(len(y_only), len(x_only)), 4)}
    ing = {c: json.loads((ROOT / "results" / f"ingest_stats_{c}.json").read_text(encoding="utf-8")) for c in "AB"}
    out["chunks"] = {c: {"n_chunks": ing[c]["ingest"]["n_chunks"], "chars_mean": ing[c]["chars"]["mean"], "chars_median": ing[c]["chars"]["median"],
                         "chars_min": ing[c]["chars"]["min"], "chars_max": ing[c]["chars"]["max"], "tokens_mean": ing[c]["tokens"]["mean"],
                         "tokens_max": ing[c]["tokens"]["max"], "seconds_embedding": ing[c]["ingest"]["seconds_embedding"],
                         "seconds_total": ing[c]["ingest"]["seconds_total"], "total_chars_indexed": ing[c]["chars"]["sum"],
                         "peak_rss_mb": ing[c]["peak_rss_mb"]} for c in "AB"}
    out["chunks"]["C"] = dict(out["chunks"]["B"], note="dùng lại chỉ mục của B (không nhúng lại)")
    out["aspects"] = json.loads((ROOT / "results" / "aspects_summary.json").read_text(encoding="utf-8"))
    out["run_meta"] = json.loads((ROOT / "results" / "run_meta.json").read_text(encoding="utf-8"))
    (ROOT / "results" / "summary.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    for c in "ABC":
        print(c, {k: (v["hit_at_1"], v["evidence_hit_at_3"], v["page_hit_at_3"]) for k, v in out["per_config"][c].items()})
    for c in "ABC":
        print(c, "by_type (h1,h3,page,n):", {k: (v["hit_at_1"], v["evidence_hit_at_3"], v["page_hit_at_3"], v["n"]) for k, v in out["by_type"][c].items()})
    for k, v in out["paired"].items():
        print(k, v)


if __name__ == "__main__":
    main()
