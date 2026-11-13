"""Chunk -> embed (model thật) -> lưu vào Chroma (persistent, cosine, metadata filter).

Chạy:  python3 -I src/ingest.py --config A --config B [--idempotency-check]

* Không có fallback: nếu không tải/chạy được model embedding, script dừng và ghi results/errors.log.
* Nạp lại cùng corpus KHÔNG nhân đôi: chunk_id xác định + text_sha256; chunk không đổi bị bỏ qua,
  chunk đổi được upsert, chunk không còn tồn tại bị xóa (stale).
* Config C không có chỉ mục riêng: dùng lại collection của B (khác biệt duy nhất là filter lúc truy vấn).
"""
import argparse
import json
import os
import platform
import resource
import statistics as st
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from chunking import PARAMS, make_chunks  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "results" / "chroma_db"
DEFAULT_MODEL = "intfloat/multilingual-e5-small"
SEED = 42


def log_error(msg: str):
    with open(ROOT / "results" / "errors.log", "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {msg}\n")


def load_units():
    return [json.loads(l) for l in open(ROOT / "data" / "corpus" / "units.jsonl", encoding="utf-8")]


class Embedder:
    """E5 cần tiền tố: 'passage: ' cho tài liệu, 'query: ' cho câu hỏi. Vector được chuẩn hóa L2."""

    def __init__(self, model_name: str):
        try:
            import numpy as np
            import torch
            import transformers
            import sentence_transformers as stz
            torch.manual_seed(SEED)
            np.random.seed(SEED)
            self.model = stz.SentenceTransformer(model_name, device="cpu")
        except Exception as e:  # ghi lỗi rõ ràng, không thay bằng vector giả
            log_error(f"Không khởi tạo được embedding model {model_name}: {e!r}")
            raise RuntimeError(f"Không khởi tạo được embedding model '{model_name}': {e}") from e
        self.name = model_name
        self.dim = self.model.get_sentence_embedding_dimension()
        self.tokenizer = self.model.tokenizer
        try:
            self.revision = self.model[0].auto_model.config._commit_hash
        except Exception:
            self.revision = None
        if not self.revision:  # dự phòng: tên thư mục snapshot trong cache HF chính là commit hash của model
            snaps = sorted((Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub").glob(
                f"models--{model_name.replace('/', '--')}/snapshots/*"))
            self.revision = snaps[-1].name if snaps else None
        self.versions = {
            "python": platform.python_version(), "sentence_transformers": stz.__version__,
            "torch": torch.__version__, "transformers": transformers.__version__, "numpy": np.__version__,
        }

    def _enc(self, texts, batch):
        return self.model.encode(texts, batch_size=batch, normalize_embeddings=True,
                                 convert_to_numpy=True, show_progress_bar=False)

    def docs(self, texts, batch=32):
        return self._enc(["passage: " + t for t in texts], batch)

    def queries(self, texts, batch=32):
        return self._enc(["query: " + t for t in texts], batch)

    def n_tokens(self, text: str) -> int:
        return len(self.tokenizer(text, add_special_tokens=False)["input_ids"])


def get_client():
    import chromadb
    DB_PATH.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(DB_PATH))


def get_collection(client, name):
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def meta_for(c, unit):
    return {
        "document_id": c.doc_id, "source": unit["source"], "page": c.unit_id, "unit_id": c.unit_id,
        "guide_section": unit["guide_section"], "section_heading": c.section_heading,
        "heading_path": unit["heading_path"], "char_start": c.char_start, "char_end": c.char_end,
        "n_chars": len(c.text), "config": c.config, "text_sha256": c.text_sha256,
    }


def ingest(cfg, units, emb, col, batch=32):
    by_id = {u["unit_id"]: u for u in units}
    t0 = time.perf_counter()
    cpu0 = time.process_time()
    chunks = [c for u in units for c in make_chunks(u, cfg)]
    t_chunk = time.perf_counter() - t0
    existing = col.get(include=["metadatas"])
    ex = {i: m.get("text_sha256") for i, m in zip(existing["ids"], existing["metadatas"])}
    new_ids = {c.chunk_id for c in chunks}
    stale = [i for i in ex if i not in new_ids]
    if stale:
        col.delete(ids=stale)
    todo = [c for c in chunks if ex.get(c.chunk_id) != c.text_sha256]
    t_embed = t_store = 0.0
    for i in range(0, len(todo), batch * 4):
        part = todo[i:i + batch * 4]
        t1 = time.perf_counter()
        vecs = emb.docs([c.text for c in part], batch)
        t_embed += time.perf_counter() - t1
        t2 = time.perf_counter()
        col.upsert(ids=[c.chunk_id for c in part], embeddings=vecs.tolist(),
                   documents=[c.text for c in part], metadatas=[meta_for(c, by_id[c.unit_id]) for c in part])
        t_store += time.perf_counter() - t2
    return chunks, {
        "n_chunks": len(chunks), "n_embedded_this_run": len(todo), "n_skipped_unchanged": len(chunks) - len(todo),
        "n_stale_deleted": len(stale), "collection_count_after": col.count(),
        "seconds_chunking": round(t_chunk, 3), "seconds_embedding": round(t_embed, 3),
        "seconds_store": round(t_store, 3), "seconds_total": round(time.perf_counter() - t0, 3),
        "cpu_seconds": round(time.process_time() - cpu0, 3),
    }


def length_stats(values):
    v = sorted(values)
    q = lambda p: v[int(p * (len(v) - 1))]
    return {"min": v[0], "p10": q(.1), "median": q(.5), "mean": round(st.mean(v), 1), "p90": q(.9), "max": v[-1], "sum": sum(v)}


def idempotency_check(cfg, units, emb, client):
    """(1) nạp lại y hệt -> không thêm bản ghi; (2) sửa 1 trang -> chỉ chunk của trang đó được nhúng lại."""
    col = get_collection(client, f"day06_{cfg}")
    _, again = ingest(cfg, units, emb, col)
    result = {"reingest_same_corpus": again, "no_duplicates": again["n_embedded_this_run"] == 0
              and again["collection_count_after"] == again["n_chunks"]}
    test_name = f"day06_{cfg}_changetest"
    try:
        client.delete_collection(test_name)
    except Exception:
        pass
    tcol = get_collection(client, test_name)
    small = [u for u in units if u["doc_id"] in {"naive_bayes", "kernel_ridge"}]
    _, first = ingest(cfg, small, emb, tcol)
    changed = [dict(u) for u in small]
    changed[0]["text"] = changed[0]["text"] + "\n\nSentence appended to simulate a document revision."
    _, second = ingest(cfg, changed, emb, tcol)
    result["document_change_simulation"] = {"first_load": first, "after_edit_of_one_page": second,
                                            "only_changed_page_reembedded": second["n_embedded_this_run"] < first["n_chunks"]}
    client.delete_collection(test_name)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", action="append", choices=["A", "B"], required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--idempotency-check", action="store_true")
    args = ap.parse_args()
    (ROOT / "results").mkdir(exist_ok=True)
    units = load_units()
    try:
        emb = Embedder(args.model)
    except RuntimeError as e:
        print("LỖI:", e, file=sys.stderr)
        sys.exit(2)
    client = get_client()
    import chromadb
    for cfg in args.config:
        col = get_collection(client, f"day06_{cfg}")
        chunks, stats = ingest(cfg, units, emb, col, args.batch)
        toks = [emb.n_tokens(c.text) for c in chunks]
        out = {
            "config": cfg, "params": PARAMS[cfg], "embedding_model": emb.name, "model_revision": emb.revision,
            "embedding_dim": emb.dim, "doc_prefix": "passage: ", "query_prefix": "query: ", "normalized_l2": True,
            "vector_store": f"chromadb {chromadb.__version__} PersistentClient, cosine (HNSW approximate)",
            "collection": f"day06_{cfg}", "db_path": "results/chroma_db", "seed": SEED,
            "chars": length_stats([len(c.text) for c in chunks]), "tokens": length_stats(toks),
            "n_chunks_over_512_tokens": sum(t + 3 > 512 for t in toks),
            "ingest": stats, "versions": {**emb.versions, "chromadb": chromadb.__version__},
            "hardware": {"cpus": os.cpu_count(), "platform": platform.platform()},
            "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "cost_usd": 0.0, "cost_note": "model chạy local, không dùng dịch vụ trả phí",
            "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if args.idempotency_check:
            out["idempotency"] = idempotency_check(cfg, units, emb, client)
        (ROOT / "results" / f"ingest_stats_{cfg}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        with open(ROOT / "results" / f"chunks_{cfg}.jsonl", "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps({"chunk_id": c.chunk_id, "unit_id": c.unit_id, "doc_id": c.doc_id, "char_start": c.char_start,
                                    "char_end": c.char_end, "section_heading": c.section_heading, "text": c.text}, ensure_ascii=False) + "\n")
        print(f"[{cfg}] {stats}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_error(traceback.format_exc())
        raise
