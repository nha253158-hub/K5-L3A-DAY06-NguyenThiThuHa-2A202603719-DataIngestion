"""Kiểm tra top-3 của Chroma (HNSW xấp xỉ) có trùng với tìm kiếm vét cạn (cosine chính xác) không.

Chạy: python3 -I src/ann_check.py  ->  results/ann_check.json
Chỉ đọc chỉ mục và vector có sẵn; câu hỏi nhúng lại bằng cùng model/prefix.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest import DEFAULT_MODEL, Embedder, get_client, get_collection  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CONFIGS = {"A": ("day06_A", False), "B": ("day06_B", False), "C": ("day06_B", True)}


def main():
    qs = json.loads((ROOT / "benchmark" / "questions.json").read_text(encoding="utf-8"))["questions"]
    emb = Embedder(DEFAULT_MODEL)
    qv = emb.queries([q["question"] for q in qs])
    client = get_client()
    res = {}
    for cname in ("day06_A", "day06_B"):
        col = get_collection(client, cname)
        got = col.get(include=["embeddings", "metadatas"])
        res[cname] = (np.array(got["embeddings"], dtype=np.float32), got["ids"], got["metadatas"])
    traces = {c: {t["question_id"]: t for t in map(json.loads, open(ROOT / "results" / f"traces_{c}.jsonl", encoding="utf-8"))} for c in CONFIGS}
    out = {"identical_top3_set": {}, "identical_top3_order": {}, "n": {}}
    for cfg, (cname, use_filter) in CONFIGS.items():
        E, ids, metas = res[cname]
        same_set = same_order = 0
        for q, v in zip(qs, qv):
            mask = np.ones(len(ids), dtype=bool)
            if use_filter and q.get("filter"):
                mask = np.array([m["guide_section"] == q["filter"]["value"] for m in metas])
            sims = E @ v
            sims = np.where(mask, sims, -9)
            top = [ids[i] for i in np.argsort(-sims)[:3]]
            chroma = [r["chunk_id"] for r in traces[cfg][q["id"]]["top3"]]
            same_set += set(top) == set(chroma)
            same_order += top == chroma
        out["identical_top3_set"][cfg], out["identical_top3_order"][cfg], out["n"][cfg] = same_set, same_order, len(qs)
    (ROOT / "results" / "ann_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
